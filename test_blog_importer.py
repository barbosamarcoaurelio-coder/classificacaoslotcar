import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from app.blog_importer import find_championship_posts, parse_blog_content
from app.main import app, require_admin
from test_ranking import championship


TITLE = "1ª etapa V Fórmula Magneto 2026"
TABLE = """<table><tr><td colspan="3">
10/11/2026 20:00:00 -- V Fórmula Magneto 2026 (GT1) Resultados
</td></tr><tr><th>Pos</th><th>Piloto</th><th>Voltas</th></tr>
<tr><td>1</td><td>Ana</td><td>200.00</td></tr></table>"""
HTML = f"<html><title>{TITLE}</title>{TABLE}</html>"


def entry(title, slug):
    return {
        "title": {"$t": title}, "content": {"$t": TABLE},
        "link": [{"rel": "alternate", "href": "https://gtautomodelismo.blogspot.com/2026/11/" + slug}],
    }


class BlogDiscoveryTests(unittest.TestCase):
    def test_feed_pagination_excludes_wrong_editions_and_unofficial_events(self):
        offsets = []

        def respond(request):
            offset = int(request.url.params["start-index"])
            offsets.append(offset)
            entries = [
                entry("1ª etapa IV Fórmula Magneto 2026", "outra-edicao"),
                entry(TITLE + " LIVRE", "livre"),
            ] if offset == 1 else [entry(TITLE, "oficial"), entry("1ª Warm-up Fórmula Magneto", "treino")]
            if offset == 1:
                entries[0]["content"]["$t"] = TABLE.replace("V Fórmula", "IV Fórmula")
            return httpx.Response(200, json={"feed": {"entry": entries, "openSearch$totalResults": {"$t": "4"}}})

        transport = httpx.MockTransport(respond)
        with patch("app.blog_importer.httpx.AsyncClient", return_value=httpx.AsyncClient(transport=transport)):
            posts = asyncio.run(find_championship_posts(championship(
                nome="V Fórmula Magneto 2026", resultados={"GT1": [{"etapa": 1}]}
            )))
        self.assertEqual(offsets, [1, 3])
        self.assertEqual([post["titulo"] for post in posts], [TITLE])
        self.assertTrue(posts[0]["ja_cadastrada"])

    def test_preview_reads_race_date_and_rejects_conflicting_tables(self):
        parsed = parse_blog_content(HTML, [])
        self.assertEqual(parsed["data_etapa"], "2026-11-10")
        self.assertEqual(parsed["etapa_num"], 1)
        self.assertEqual(len(parse_blog_content(HTML + TABLE, [])["subdivisoes"]["GT1"]), 1)
        with self.assertRaisesRegex(ValueError, "resultados diferentes"):
            parse_blog_content(HTML + TABLE.replace("Ana", "Bia"), [])

    def test_admin_search_and_preview_do_not_publish_without_save(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "DB_PATH": str(Path(directory) / "blog.db"), "DATABASE_URL": "",
        }):
            with TestClient(app) as client:
                self.assertEqual(client.post("/api/championships/1/blog-search").status_code, 401)
                app.dependency_overrides[require_admin] = lambda: {"is_admin": True}
                try:
                    before = client.get("/api/data").json()
                    camp = before["championships"][0]
                    with patch("app.main.find_championship_posts", new_callable=AsyncMock) as search:
                        search.return_value = [{"titulo": TITLE, "url": "https://gtautomodelismo.blogspot.com/post", "etapa": 1}]
                        response = client.post(f"/api/championships/{camp['id']}/blog-search")
                        self.assertEqual(response.status_code, 200)
                        search.assert_awaited_once()
                    response = client.post("/api/blog/fetch-and-parse", json={
                        "championship_id": camp["id"], "raw_text": HTML,
                    })
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(response.json()["data_etapa"], "2026-11-10")
                    self.assertEqual(client.get("/api/data").json(), before)
                    with patch("app.main.find_championship_posts", side_effect=httpx.ConnectError("indisponível")):
                        response = client.post(f"/api/championships/{camp['id']}/blog-search")
                        self.assertEqual(response.status_code, 502)
                        self.assertIn("Não foi possível", response.json()["detail"])
                finally:
                    app.dependency_overrides.clear()


if __name__ == "__main__":
    unittest.main()
