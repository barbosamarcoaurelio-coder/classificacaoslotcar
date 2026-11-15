import re
import unicodedata
import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from typing import Dict, List, Any, Tuple, Optional
import difflib

BLOG_FEED_URL = "https://gtautomodelismo.blogspot.com/feeds/posts/default"


def championship_search_tokens(text: str) -> set:
    text = re.sub(r"(?<=\d)(?=[a-z])|(?<=[a-z])(?=\d)", " ", normalize_str(text))
    return set(text.split()) - {"campeonato", "de", "da", "do", "dos"}


async def find_championship_posts(championship: Dict[str, Any]) -> List[Dict[str, Any]]:
    required = championship_search_tokens(championship["nome"])
    posts = {}
    offset = 1
    params = {
        "alt": "json", "max-results": 50,
        "published-min": championship["inicio"] + "T00:00:00-03:00",
        "published-max": datetime.now(timezone.utc).isoformat(),
    }
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        while True:
            response = await client.get(BLOG_FEED_URL, params={**params, "start-index": offset})
            response.raise_for_status()
            feed = response.json()["feed"]
            entries = feed.get("entry", [])
            total = int(feed["openSearch$totalResults"]["$t"])
            if not entries:
                if offset <= total:
                    raise ValueError("O blog retornou uma página incompleta. Tente novamente.")
                break
            for entry in entries:
                title = entry["title"]["$t"]
                if re.search(r"\blivre\b|warm.?up|treino|duplas|endurance", normalize_str(title)):
                    continue
                stage_match = re.search(r"\b(\d+)\s*[ªºa]?\s*etapa\b", title, re.I)
                if not stage_match or not 1 <= int(stage_match[1]) <= championship["etapas"]:
                    continue
                html = entry.get("content", {}).get("$t", "")
                soup = BeautifulSoup(html, "html.parser")
                headers = [
                    table.get_text(" ", strip=True).split("Resultados", 1)[0]
                    for table in soup.find_all("table")
                    if "Resultados" in table.get_text() and "Piloto" in table.get_text()
                ]
                if not any(required <= championship_search_tokens(title + " " + header) for header in headers):
                    continue
                link = next((x["href"] for x in entry["link"] if x["rel"] == "alternate"), None)
                if not link or not link.startswith("https://gtautomodelismo.blogspot.com/"):
                    raise ValueError("A publicação não contém um link válido do blog oficial.")
                stage = int(stage_match[1])
                posts[link] = {
                    "titulo": title, "url": link, "etapa": stage,
                    "ja_cadastrada": any(
                        result["etapa"] == stage
                        for results in championship["resultados"].values() for result in results
                    ),
                }
            offset += len(entries)
            if offset > total:
                break
    return sorted(posts.values(), key=lambda post: (post["etapa"], post["titulo"]), reverse=True)

def normalize_str(s: str) -> str:
    if not s:
        return ""
    s = s.strip()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^\w\s]", "", s)
    return re.sub(r"\s+", " ", s).lower().strip()

def find_similar_pilot(nome_blog: str, todos_pilotos: List[Dict[str, Any]]) -> Optional[str]:
    norm_blog = normalize_str(nome_blog)
    nomes_cadastrados = [p["nome"] for p in todos_pilotos]
    
    for nome in nomes_cadastrados:
        norm_cad = normalize_str(nome)
        ratio = difflib.SequenceMatcher(None, norm_blog, norm_cad).ratio()
        if ratio >= 0.75 and norm_blog != norm_cad:
            return nome
    return None

def match_pilot(
    nome_blog: str,
    pilotos_cadastrados: List[Dict[str, Any]],
    categoria_nome: Optional[str] = None,
    subdivisao_nome: Optional[str] = None,
    pilotos_outras_subs: Optional[Dict[str, str]] = None # nome -> subdivisao onde já corre
) -> Tuple[Optional[str], str, Optional[str]]:
    """
    Retorna: (piloto_nome_resolvido, metodo, aviso)
    metodos: 'exato', 'apelido', 'prefixo_unico', 'desconhecido'
    """
    norm_blog = normalize_str(nome_blog)
    
    # 1. Exact match com nome
    for p in pilotos_cadastrados:
        if normalize_str(p["nome"]) == norm_blog:
            aviso = None
            if pilotos_outras_subs and p["nome"] in pilotos_outras_subs:
                sub_atual = pilotos_outras_subs[p["nome"]]
                if subdivisao_nome and sub_atual != subdivisao_nome:
                    aviso = f"Atenção: Piloto '{p['nome']}' já está cadastrado na {sub_atual} deste campeonato."
            return p["nome"], "exato", aviso
            
    # 2. Match com apelidos conhecidos
    for p in pilotos_cadastrados:
        for ap in p.get("apelidos_no_blog", []):
            if normalize_str(ap) == norm_blog:
                aviso = None
                if pilotos_outras_subs and p["nome"] in pilotos_outras_subs:
                    sub_atual = pilotos_outras_subs[p["nome"]]
                    if subdivisao_nome and sub_atual != subdivisao_nome:
                        aviso = f"Atenção: Piloto '{p['nome']}' já está cadastrado na {sub_atual} deste campeonato."
                return p["nome"], "apelido", aviso
                
    # 3. Match de prefixo único
    candidatos_prefixo = []
    for p in pilotos_cadastrados:
        norm_p = normalize_str(p["nome"])
        primeira_palavra = norm_p.split()[0] if norm_p else ""
        if primeira_palavra == norm_blog or norm_p.startswith(norm_blog + " "):
            candidatos_prefixo.append(p["nome"])
            
    if len(candidatos_prefixo) == 1:
        piloto_nome = candidatos_prefixo[0]
        aviso = None
        if pilotos_outras_subs and piloto_nome in pilotos_outras_subs:
            sub_atual = pilotos_outras_subs[piloto_nome]
            if subdivisao_nome and sub_atual != subdivisao_nome:
                aviso = f"Atenção: Piloto '{piloto_nome}' já está cadastrado na {sub_atual} deste campeonato."
        return piloto_nome, "prefixo_unico", aviso
        
    # Verificar se é parecido com algum piloto existente
    similar = find_similar_pilot(nome_blog, pilotos_cadastrados)
    aviso = None
    if similar:
        aviso = f"Nome similar ao piloto existente '{similar}'. Confirme se é a mesma pessoa."
        
    return None, "desconhecido", aviso

async def fetch_blog_html(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            raise Exception(f"Erro HTTP {resp.status_code} ao buscar link do blog.")
        return resp.text

def parse_blog_content(
    html_or_text: str,
    pilotos_cadastrados: List[Dict[str, Any]],
    campeonato_nome: Optional[str] = None,
    categoria_nome: Optional[str] = None,
    pilotos_por_sub: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    soup = BeautifulSoup(html_or_text, "html.parser")
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    
    if not title:
        # tentar pegar primeiro h1, h2 ou linha
        h = soup.find(["h1", "h2", "h3"])
        if h:
            title = h.get_text(strip=True)
        else:
            title = html_or_text.split("\n")[0][:100].strip()
            
    # Extrair número da etapa
    etapa_match = re.search(r"(\d+)[\ª\ºªºa-zA-Z\s]*\s*etapa", title, re.IGNORECASE)
    etapa_num = int(etapa_match.group(1)) if etapa_match else None
    
    # Alerta se não citar o campeonato
    alerta_campeonato = None
    if campeonato_nome and normalize_str(campeonato_nome) not in normalize_str(title):
        if categoria_nome and normalize_str(categoria_nome) not in normalize_str(title):
            alerta_campeonato = f"Aviso: O título '{title}' não cita explicitamente o campeonato '{campeonato_nome}'."
            
    tables = soup.find_all("table")
    subdivisoes_encontradas: Dict[str, List[Dict[str, Any]]] = {}
    dates = set()
    warnings = []
    
    for t in tables:
        txt = t.get_text("\n", strip=True)
        if "Resultados" not in txt or "Piloto" not in txt:
            continue
        race_date = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", txt.split("Resultados", 1)[0])
        if race_date:
            dates.add(datetime.strptime(race_date[1], "%d/%m/%Y").date().isoformat())
            
        sub_match = re.search(r"\b(GT[123])\b", txt, re.IGNORECASE)
        if not sub_match:
            prev = t.find_previous(["h1", "h2", "h3", "h4", "p", "div", "b"])
            if prev:
                sub_match = re.search(r"\b(GT[123])\b", prev.get_text(), re.IGNORECASE)
                
        sub_nome = sub_match.group(1).upper() if sub_match else "GT1"
        if not sub_match:
            warnings.append("A fonte não informa a subdivisão. GT1 foi sugerida; confirme antes de salvar.")
        
        linhas_pilotos = []
        rows = t.find_all("tr")
        for r in rows:
            cols = [c.get_text(strip=True) for c in r.find_all(["td", "th"])]
            if len(cols) >= 3 and cols[0].isdigit():
                pos = int(cols[0])
                nome_bruto = cols[1]
                total_voltas = cols[2]
                
                piloto_resolvido, metodo, aviso = match_pilot(
                    nome_bruto,
                    pilotos_cadastrados,
                    categoria_nome,
                    sub_nome,
                    pilotos_por_sub
                )
                
                linhas_pilotos.append({
                    "pos_no_blog": pos,
                    "nome_no_blog": nome_bruto,
                    "total_voltas": total_voltas,
                    "piloto": piloto_resolvido or nome_bruto,
                    "reconhecido": piloto_resolvido is not None,
                    "metodo": metodo,
                    "aviso": aviso
                })
                
        if linhas_pilotos:
            if sub_nome in subdivisoes_encontradas:
                previous = subdivisoes_encontradas[sub_nome]
                if [(p["nome_no_blog"], p["total_voltas"]) for p in previous] != [
                    (p["nome_no_blog"], p["total_voltas"]) for p in linhas_pilotos
                ]:
                    raise ValueError(f"O post contém resultados diferentes para {sub_nome}. Escolha uma publicação com apenas a fase desejada.")
            subdivisoes_encontradas[sub_nome] = linhas_pilotos
            
    # Se nenhuma tabela HTML foi encontrada (ex.: usuário colou texto puro)
    if not subdivisoes_encontradas:
        subdivisoes_encontradas = parse_plain_text_results(
            html_or_text,
            pilotos_cadastrados,
            categoria_nome,
            pilotos_por_sub
        )
        
    if len(dates) > 1:
        raise ValueError("O post contém mais de uma data de corrida. Confira a fonte antes de importar.")
    if not dates:
        warnings.append("Data da corrida não identificada no post. Volte e confira a data antes de salvar.")
    return {
        "titulo": title,
        "data_etapa": next(iter(dates), None),
        "etapa_num": etapa_num,
        "alerta_campeonato": " ".join(dict.fromkeys(([alerta_campeonato] if alerta_campeonato else []) + warnings)) or None,
        "subdivisoes": subdivisoes_encontradas
    }

def parse_plain_text_results(
    text: str,
    pilotos_cadastrados: List[Dict[str, Any]],
    categoria_nome: Optional[str] = None,
    pilotos_por_sub: Optional[Dict[str, str]] = None
) -> Dict[str, List[Dict[str, Any]]]:
    """Parser para texto puro colado quando o link falhar."""
    lines = text.split("\n")
    subdivisoes: Dict[str, List[Dict[str, Any]]] = {}
    current_sub = "GT1"
    
    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue
            
        sub_match = re.search(r"\b(GT[123])\b", line_clean, re.IGNORECASE)
        if sub_match:
            current_sub = sub_match.group(1).upper()
            if current_sub not in subdivisoes:
                subdivisoes[current_sub] = []
            continue
            
        # Padrão: "1 Moch 181.63" ou "1 - Moch" ou "1. Moch"
        m = re.match(r"^(\d+)[\.\s\-\–\)]+([a-zA-ZÀ-ÿ\s\.\']+?)(?:\s+(\d+[\.\,]\d+.*))?$", line_clean)
        if m:
            pos = int(m.group(1))
            nome_bruto = m.group(2).strip()
            total_voltas = m.group(3).strip() if m.group(3) else ""
            
            if current_sub not in subdivisoes:
                subdivisoes[current_sub] = []
                
            piloto_resolvido, metodo, aviso = match_pilot(
                nome_bruto,
                pilotos_cadastrados,
                categoria_nome,
                current_sub,
                pilotos_por_sub
            )
            
            subdivisoes[current_sub].append({
                "pos_no_blog": pos,
                "nome_no_blog": nome_bruto,
                "total_voltas": total_voltas,
                "piloto": piloto_resolvido or nome_bruto,
                "reconhecido": piloto_resolvido is not None,
                "metodo": metodo,
                "aviso": aviso
            })
            
    return subdivisoes
