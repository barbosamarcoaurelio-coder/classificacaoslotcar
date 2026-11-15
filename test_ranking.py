import copy
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.db import export_backup_json, get_db, init_db, restore_backup_json
from app.main import app, require_admin
from app.ranking import calculate_rankings, identify_ranking_category


TABLES = [{"nome": "Padrão", "pontos_por_posicao": [30, 28, 24, 0]}]


def championship(**overrides):
    data = {
        "nome": "Copa",
        "categoria": "Qualquer nome",
        "ranking_categoria": "formula1",
        "inicio": "2026-08-04",
        "etapas": 6,
        "descartes": 1,
        "periodicidade": "semanal",
        "ultima_etapa_em_dobro": True,
        "tabela_pontuacao": "Padrão",
        "datas_das_etapas": ["2026-08-04"],
        "subdivisoes": [{"subdivisao": "GT1"}],
        "resultados": {"GT1": [stage(1, ["Ana"])]},
    }
    data.update(overrides)
    return data


def stage(number, pilots, day="2026-08-04", **extra):
    return {"etapa": number, "data": day, "ordem_de_chegada": pilots, **extra}


def rows(championships, category="formula1", tables=None):
    return calculate_rankings(championships, tables or TABLES)["rankings"][category]


class RankingCalculationTests(unittest.TestCase):
    def test_unconfirmed_rules_do_not_influence_performance(self):
        data = calculate_rankings([
            championship(regras_confirmadas=False, resultados={"Geral": [stage(1, ["Ana"])]}),
            championship(nome="Conferido"),
        ], TABLES)
        self.assertEqual(data["rankings"]["formula1"][0]["participacoes"], 1)
        self.assertEqual(data["rankings"]["formula1"][0]["indice"], 300)
        self.assertIn("fora do ranking", data["avisos"][0])

    def test_double_final_and_discarded_results_still_count(self):
        camp = championship(etapas=2, resultados={"GT2": [
            stage(1, ["Bia", "Caio", "Ana"]),
            stage(2, ["Ana"]),
        ]})
        original = copy.deepcopy(camp)
        ana = next(row for row in rows([camp]) if row["piloto"] == "Ana")
        self.assertAlmostEqual(ana["indice"], 100 * (24 * 2 + 60 * 2) / 90)
        self.assertEqual(ana["participacoes"], 2)
        self.assertEqual(camp, original)
        camp["ultima_etapa_em_dobro"] = False
        ana = next(row for row in rows([camp]) if row["piloto"] == "Ana")
        self.assertEqual(ana["indice"], 180)

    def test_absence_zero_points_cutoff_and_simulation(self):
        camp = championship(resultados={"GT3": [
            stage(1, ["Antes"], "2026-07-31"),
            stage(2, ["Ana", "Bia", "Caio", "Zero"], "2026-08-01"),
            stage(3, ["Ana"]),
            stage(4, ["Simulado"], simulada=True),
        ]})
        result = {row["piloto"]: row for row in rows([camp])}
        self.assertEqual(set(result), {"Ana", "Bia", "Caio", "Zero"})
        self.assertEqual(result["Ana"]["indice"], 100)
        self.assertEqual(result["Ana"]["participacoes"], 2)
        self.assertEqual(result["Bia"]["participacoes"], 1)
        self.assertEqual(result["Zero"]["participacoes"], 1)
        self.assertEqual(result["Zero"]["indice"], 0)

    def test_historical_divisions_and_independent_categories(self):
        camp = championship(resultados={
            "GT1": [stage(1, ["Ana"])],
            "GT3": [stage(2, ["Ana"])],
        })
        another = championship(nome="Outra copa", resultados={"GT2": [stage(1, ["Ana"])]})
        magneto = championship(ranking_categoria="magneto")
        brushless = championship(ranking_categoria="brushless")
        result = calculate_rankings([camp, another, magneto, brushless], TABLES)
        self.assertEqual(result["rankings"]["formula1"][0]["indice"], 200)
        self.assertEqual(result["rankings"]["formula1"][0]["participacoes"], 3)
        self.assertEqual(result["rankings"]["magneto"][0]["participacoes"], 1)
        self.assertEqual(result["rankings"]["brushless"][0]["participacoes"], 1)

    def test_fewer_participations_and_shared_positions(self):
        camp = championship(resultados={"GT1": [
            stage(1, ["Ana"]), stage(2, ["Bia"]),
            stage(3, ["Caio"]), stage(4, ["Caio"]),
            stage(5, ["Auxiliar", "Dani"]),
        ]})
        result = rows([camp])
        self.assertEqual(
            [(row["piloto"], row["pos"]) for row in result],
            [("Ana", 1), ("Auxiliar", 1), ("Bia", 1), ("Caio", 4), ("Dani", 5)]
        )

    def test_order_uses_exact_index_not_rounded_display(self):
        def many_races(count, pilot):
            return championship(
                nome=pilot, etapas=count + 1,
                resultados={"GT1": [
                    stage(i, ["Auxiliar", pilot] if i == 1 else [pilot])
                    for i in range(1, count + 1)
                ]}
            )
        result = rows(
            [many_races(1000, "Menos"), many_races(1001, "Mais")],
            tables=[{"nome": "Padrão", "pontos_por_posicao": [30, 29]}]
        )
        ranked = [row for row in result if row["piloto"] != "Auxiliar"]
        self.assertEqual([row["piloto"] for row in ranked], ["Mais", "Menos"])
        self.assertEqual(round(ranked[0]["indice"], 2), round(ranked[1]["indice"], 2))
        self.assertNotEqual(ranked[0]["pos"], ranked[1]["pos"])

    def test_category_identification_ignores_championship_name(self):
        self.assertEqual(identify_ranking_category(
            {"categoria": "Outra", "inicio": "2026-08-04", "nome": "Magneto"}
        ), "formula1")
        self.assertEqual(identify_ranking_category(
            {"categoria": "Outra", "inicio": "2026-08-06"}
        ), "magneto")
        self.assertEqual(identify_ranking_category(
            {"categoria": "Brushless", "inicio": "2026-08-04"}
        ), "brushless")
        self.assertIsNone(identify_ranking_category(
            {"categoria": "Outra", "inicio": "2026-08-05"}
        ))

    def test_invalid_results_are_reported_instead_of_wrong_ranking(self):
        for results in [
            {"GT4": [stage(1, ["Ana"])]},
            {"GT1": [stage(1, ["Ana", "Ana"])]},
            {"GT1": [stage(1, ["Ana"])], "GT2": [stage(1, ["Ana"])]},
            {"GT1": [stage(1, ["Ana"], "data incorreta")]},
        ]:
            with self.subTest(results=results), self.assertRaises(ValueError):
                rows([championship(resultados=results)])
        data = calculate_rankings([championship(ranking_categoria=None)], TABLES)
        self.assertEqual(data["rankings"]["formula1"], [])
        self.assertIn("Copa", data["avisos"][0])


class RankingPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {
            "DB_PATH": str(Path(self.directory.name) / "test.db"),
            "DATABASE_URL": "",
        })
        self.environment.start()
        app.dependency_overrides[require_admin] = lambda: {"is_admin": True}

    def tearDown(self):
        app.dependency_overrides.clear()
        self.environment.stop()
        self.directory.cleanup()

    def test_legacy_migration_preserves_data_and_ranking_after_reschedule(self):
        conn = sqlite3.connect(os.environ["DB_PATH"])
        conn.execute("""CREATE TABLE championships (
            id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE NOT NULL,
            categoria TEXT NOT NULL, inicio TEXT NOT NULL, etapas INTEGER NOT NULL,
            descartes INTEGER NOT NULL, periodicidade TEXT NOT NULL,
            ultima_etapa_em_dobro INTEGER NOT NULL, tabela_pontuacao TEXT NOT NULL,
            datas_das_etapas TEXT NOT NULL, subdivisoes TEXT NOT NULL,
            resultados TEXT NOT NULL, fontes_blog TEXT NOT NULL, auditoria TEXT NOT NULL
        )""")
        conn.execute("""INSERT INTO championships VALUES (
            7, 'Legado', 'Outra', '2026-08-04', 6, 1, 'semanal', 1,
            'Padrão', '[]', '[]', '{}', '{}', '{}')""")
        conn.commit()
        conn.close()
        init_db()
        conn = get_db()
        row = conn.execute("SELECT * FROM championships WHERE id = 7").fetchone()
        self.assertEqual(row["ranking_categoria"], "formula1")
        self.assertEqual(row["resultados"], "{}")
        conn.execute("UPDATE championships SET inicio = '2026-08-06' WHERE id = 7")
        conn.commit()
        conn.close()
        init_db()
        conn = get_db()
        self.assertEqual(conn.execute(
            "SELECT ranking_categoria FROM championships WHERE id = 7"
        ).fetchone()["ranking_categoria"], "formula1")
        conn.close()

    def test_api_create_edit_results_backup_restore_and_delete(self):
        with TestClient(app) as client:
            payload = championship(nome="Teste API")
            payload["tabela_pontuacao"] = "Padrão GT Racing"
            payload.pop("resultados")
            response = client.post("/api/championships", json=payload)
            self.assertEqual(response.status_code, 200, response.text)
            camp_id = response.json()["id"]
            result = {
                "championship_id": camp_id, "etapa": 1, "data": "2026-08-04",
                "resultados_por_subdivisao": {"GT1": ["Piloto Teste"]},
            }
            self.assertEqual(client.post("/api/stages/save-results", json=result).status_code, 200)

            def pilot_rows():
                response = client.get("/api/rankings")
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.headers["cache-control"], "no-store")
                return [
                    row for row in response.json()["rankings"]["formula1"]
                    if row["piloto"] == "Piloto Teste"
                ]

            self.assertEqual(pilot_rows()[0]["indice"], 300)
            result["resultados_por_subdivisao"] = {"GT1": ["Outro Teste", "Piloto Teste"]}
            client.post("/api/stages/save-results", json=result).raise_for_status()
            self.assertEqual(pilot_rows()[0]["indice"], 280)
            payload.pop("ranking_categoria")
            payload["inicio"] = "2026-08-06"
            client.put(f"/api/championships/{camp_id}", json=payload).raise_for_status()
            client.post(f"/api/championships/{camp_id}/reschedule-stage", json={
                "etapa": 1, "nova_data": "2026-08-13"
            }).raise_for_status()
            self.assertEqual(pilot_rows()[0]["indice"], 280)
            backup = export_backup_json()
            saved = next(c for c in backup["campeonatos"] if c["nome"] == "Teste API")
            self.assertEqual(saved["ranking_categoria"], "formula1")
            restore_backup_json(backup)
            init_db()
            self.assertEqual(pilot_rows()[0]["indice"], 280)
            data = client.get("/api/data").json()
            restored_id = next(c["id"] for c in data["championships"] if c["nome"] == "Teste API")
            client.delete(f"/api/championships/{restored_id}").raise_for_status()
            self.assertEqual(pilot_rows(), [])

    def test_pending_rules_survive_edits_restore_and_restart(self):
        with TestClient(app) as client:
            payload = championship(
                nome="Histórico pendente", regras_confirmadas=False,
                tabela_pontuacao="Padrão GT Racing",
            )
            response = client.post("/api/championships", json=payload)
            response.raise_for_status()
            camp_id = response.json()["id"]
            client.post("/api/stages/save-results", json={
                "championship_id": camp_id, "etapa": 1, "data": "2026-08-04",
                "resultados_por_subdivisao": {"GT1": ["Piloto Histórico"]},
            }).raise_for_status()
            classification = client.get(f"/api/classification/{camp_id}/GT1").json()
            self.assertFalse(classification["regras_confirmadas"])
            payload.pop("regras_confirmadas")
            client.put(f"/api/championships/{camp_id}", json=payload).raise_for_status()
            backup = export_backup_json()
            self.assertFalse(next(
                c for c in backup["campeonatos"] if c["nome"] == payload["nome"]
            )["regras_confirmadas"])
            restore_backup_json(backup)
            init_db()
            ranking = client.get("/api/rankings").json()
            self.assertNotIn("Piloto Histórico", [
                row["piloto"] for row in ranking["rankings"]["formula1"]
            ])
            self.assertTrue(any("Histórico pendente" in warning for warning in ranking["avisos"]))
            data = client.get("/api/data").json()
            restored_id = next(c["id"] for c in data["championships"] if c["nome"] == payload["nome"])
            payload["regras_confirmadas"] = True
            client.put(f"/api/championships/{restored_id}", json=payload).raise_for_status()
            ranking = client.get("/api/rankings").json()
            self.assertIn("Piloto Histórico", [
                row["piloto"] for row in ranking["rankings"]["formula1"]
            ])

    def test_legacy_backup_infers_category_and_explicit_choice_survives(self):
        with TestClient(app):
            backup = export_backup_json()
            backup["campeonatos"] = [
                championship(ranking_categoria="brushless", inicio="2026-08-04"),
                championship(nome="Legado quinta", ranking_categoria=None, inicio="2026-08-06"),
            ]
            restore_backup_json(backup)
            result = export_backup_json()["campeonatos"]
            self.assertEqual([c["ranking_categoria"] for c in result], ["brushless", "magneto"])

    def test_api_rejects_unknown_category_and_reports_invalid_results(self):
        with TestClient(app) as client:
            payload = championship(ranking_categoria="invalido")
            self.assertEqual(client.post("/api/championships", json=payload).status_code, 422)
            payload.update(ranking_categoria=None, inicio="2026-08-05")
            self.assertEqual(client.post("/api/championships", json=payload).status_code, 422)
            conn = get_db()
            conn.cursor().execute(
                "UPDATE championships SET resultados = ? WHERE id = ?",
                (json.dumps({"GT4": [stage(1, ["Ana"])]}), 1)
            )
            conn.commit()
            conn.close()
            response = client.get("/api/rankings")
            self.assertEqual(response.status_code, 422)
            self.assertIn("GT4", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
