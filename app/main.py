import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Literal

import httpx
from fastapi import FastAPI, Depends, HTTPException, Request, Response, status, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from pydantic import BaseModel
from app.ranking import RankingCategory, calculate_rankings, identify_ranking_category

from app.db import (
    init_db, get_db, export_backup_json, restore_backup_json, generate_calendar
)
from app.auth import (
    verify_password, hash_password, create_session_token, verify_session_token
)
from app.scoring import (
    calculate_classification, generate_export_html
)
from app.blog_importer import (
    fetch_blog_html, parse_blog_content, find_championship_posts, normalize_str
)

app = FastAPI(title="Classificação Geral · GT Racing Slot Car")

# Montar arquivos estáticos
STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Inicialização do banco no startup
@app.on_event("startup")
def on_startup():
    init_db()

# Autenticação dependência
def get_current_user(request: Request, authorization: Optional[str] = Header(None)) -> Optional[dict]:
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
    elif "session_token" in request.cookies:
        token = request.cookies.get("session_token")
        
    if not token:
        return None
    return verify_session_token(token)

def require_admin(user: Optional[dict] = Depends(get_current_user)):
    if not user or not user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Acesso restrito para administradores."
        )
    return user

# Rotas Públicas Principais
@app.get("/", response_class=HTMLResponse)
def index_page():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Classificação Geral · GT Racing Slot Car</h1>"

@app.get("/manifest.json")
def pwa_manifest():
    return FileResponse(os.path.join(STATIC_DIR, "manifest.json"), media_type="application/manifest+json")

@app.get("/sw.js")
def service_worker():
    return FileResponse(os.path.join(STATIC_DIR, "sw.js"), media_type="application/javascript")

@app.get("/apple-touch-icon.png")
def apple_icon():
    return FileResponse(os.path.join(STATIC_DIR, "apple-touch-icon.png"), media_type="image/png")

@app.get("/health")
def health_check():
    return {"status": "ok", "app": "GT Racing Slot Car", "time": datetime.now().isoformat()}

# Autenticação Endpoints
class LoginRequest(BaseModel):
    email: str
    password: str

@app.post("/api/auth/login")
def login(req: LoginRequest, response: Response):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE email = ?", (req.email,))
    user = c.fetchone()
    conn.close()
    
    if not user or not verify_password(user["password_hash"], req.password):
        raise HTTPException(status_code=400, detail="E-mail ou senha inválidos.")
        
    token = create_session_token(user["email"], bool(user["is_admin"]))
    response.set_cookie(
        key="session_token",
        value=token,
        max_age=86400 * 30,
        httponly=True,
        samesite="lax"
    )
    return {"token": token, "email": user["email"], "is_admin": bool(user["is_admin"])}

@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie("session_token")
    return {"ok": True}

@app.get("/api/auth/me")
def get_me(user: Optional[dict] = Depends(get_current_user)):
    if not user:
        return {"authenticated": False, "is_admin": False}
    return {"authenticated": True, "email": user["email"], "is_admin": user.get("is_admin", False)}

# Obter todos os dados do sistema para a interface
@app.get("/api/data")
def get_all_data():
    conn = get_db()
    c = conn.cursor()
    
    c.execute("SELECT * FROM categories ORDER BY id ASC")
    categories = [
        {"id": r["id"], "nome": r["nome"], "subdivisoes": json.loads(r["subdivisoes"])}
        for r in c.fetchall()
    ]
    
    c.execute("SELECT * FROM scoring_tables ORDER BY id ASC")
    scoring_tables = [
        {
            "id": r["id"],
            "nome": r["nome"],
            "pontos_por_posicao": json.loads(r["pontos_por_posicao"]),
            "regra_alem_da_tabela": r["regra_alem_da_tabela"]
        }
        for r in c.fetchall()
    ]
    
    c.execute("SELECT * FROM pilots ORDER BY nome ASC")
    pilots = [
        {
            "id": r["id"],
            "nome": r["nome"],
            "apelidos_no_blog": json.loads(r["apelidos"]),
            "provas": json.loads(r["provas"])
        }
        for r in c.fetchall()
    ]
    
    c.execute("SELECT * FROM championships ORDER BY id ASC")
    championships = []
    for r in c.fetchall():
        championships.append({
            "id": r["id"],
            "nome": r["nome"],
            "categoria": r["categoria"],
            "ranking_categoria": r["ranking_categoria"],
            "regras_confirmadas": bool(r["regras_confirmadas"]),
            "situacao": r["situacao"],
            "incluir_no_ranking": bool(r["incluir_no_ranking"]),
            "inicio": r["inicio"],
            "etapas": r["etapas"],
            "descartes": r["descartes"],
            "periodicidade": r["periodicidade"],
            "ultima_etapa_em_dobro": bool(r["ultima_etapa_em_dobro"]),
            "tabela_pontuacao": r["tabela_pontuacao"],
            "datas_das_etapas": json.loads(r["datas_das_etapas"]),
            "subdivisoes": json.loads(r["subdivisoes"]),
            "resultados": json.loads(r["resultados"]),
            "fontes_blog": json.loads(r["fontes_blog"]),
            "auditoria": json.loads(r["auditoria"])
        })
        
    conn.close()
    return {
        "categories": categories,
        "scoring_tables": scoring_tables,
        "pilots": pilots,
        "championships": championships
    }

@app.get("/api/rankings")
def get_rankings(response: Response):
    response.headers["Cache-Control"] = "no-store"
    data = get_all_data()
    try:
        return calculate_rankings(data["championships"], data["scoring_tables"])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# Classificação por campeonato e subdivisão
@app.get("/api/classification/{championship_id}/{subdivisao}")
def get_classification(
    championship_id: int,
    subdivisao: str,
    simulacao: bool = False,
    max_etapa: Optional[int] = None
):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM championships WHERE id = ?", (championship_id,))
    row = c.fetchone()
    if not row:
        c.execute("SELECT * FROM championships ORDER BY id ASC LIMIT 1")
        row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Campeonato não encontrado.")
        
    camp = {
        "id": row["id"],
        "nome": row["nome"],
        "categoria": row["categoria"],
        "inicio": row["inicio"],
        "etapas": row["etapas"],
        "descartes": row["descartes"],
        "periodicidade": row["periodicidade"],
        "ultima_etapa_em_dobro": bool(row["ultima_etapa_em_dobro"]),
        "tabela_pontuacao": row["tabela_pontuacao"],
        "datas_das_etapas": json.loads(row["datas_das_etapas"]),
        "subdivisoes": json.loads(row["subdivisoes"]),
        "resultados": json.loads(row["resultados"]),
    }
    
    c.execute("SELECT * FROM scoring_tables WHERE nome = ?", (camp["tabela_pontuacao"],))
    stab = c.fetchone()
    if stab:
        tabela = {
            "nome": stab["nome"],
            "pontos_por_posicao": json.loads(stab["pontos_por_posicao"])
        }
    else:
        tabela = {"nome": "Padrão GT Racing", "pontos_por_posicao": [30, 28, 26, 25, 24, 23, 22, 21, 20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9]}
        
    conn.close()
    
    result = calculate_classification(
        camp,
        subdivisao,
        tabela,
        max_etapa=max_etapa,
        simulacao=simulacao
    )
    result["regras_confirmadas"] = bool(row["regras_confirmadas"])
    return result

@app.get("/api/classification/{championship_id}/{subdivisao}/export-html", response_class=HTMLResponse)
def export_html_endpoint(championship_id: int, subdivisao: str):
    res = get_classification(championship_id, subdivisao)
    return generate_export_html(res)

# Importação de Blog
class BlogFetchRequest(BaseModel):
    url: Optional[str] = None
    raw_text: Optional[str] = None
    championship_id: int
    etapa: Optional[int] = None

@app.post("/api/blog/fetch-and-parse")
async def blog_fetch_and_parse(req: BlogFetchRequest, admin: dict = Depends(require_admin)):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM championships WHERE id = ?", (req.championship_id,))
    camp_row = c.fetchone()
    if not camp_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Campeonato não encontrado.")
        
    camp_nome = camp_row["nome"]
    cat_nome = camp_row["categoria"]
    
    c.execute("SELECT * FROM pilots")
    pilotos = [
        {"nome": r["nome"], "apelidos_no_blog": json.loads(r["apelidos"])}
        for r in c.fetchall()
    ]
    
    pilotos_por_sub = {}
    resultados = json.loads(camp_row["resultados"])
    etapas = sorted(
        (
            (resultado["etapa"], sub, resultado)
            for sub, resultados_sub in resultados.items()
            for resultado in resultados_sub
        ),
        key=lambda item: item[0],
    )
    for _, sub, resultado in etapas:
        for piloto in resultado.get("ordem_de_chegada", []):
            pilotos_por_sub[piloto] = sub
                
    conn.close()
    
    html_content = ""
    if req.url:
        try:
            html_content = await fetch_blog_html(req.url)
        except Exception as e:
            if not req.raw_text:
                raise HTTPException(status_code=400, detail=f"Erro ao buscar link: {str(e)}. Use a opção de colar texto da página.")
                
    if not html_content and req.raw_text:
        html_content = req.raw_text
        
    if not html_content:
        raise HTTPException(status_code=400, detail="Forneça uma URL válida ou cole o texto do post.")
        
    try:
        parsed = parse_blog_content(
            html_content,
            pilotos,
            campeonato_nome=camp_nome,
            categoria_nome=cat_nome,
            pilotos_por_sub=pilotos_por_sub
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    
    return parsed

@app.post("/api/championships/{championship_id}/blog-search")
async def search_championship_blog(championship_id: int, admin: dict = Depends(require_admin)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM championships WHERE id = ?", (championship_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Campeonato não encontrado.")
    championship = dict(row)
    championship["resultados"] = json.loads(row["resultados"])
    try:
        posts = await find_championship_posts(championship)
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(
            status_code=502, detail="Não foi possível consultar os resultados do blog. Tente novamente ou cole o link do post."
        ) from exc
    return {"posts": posts}

# Salvar Resultado de Etapa (Manual ou via Importação do Blog)
class SaveStageResultsRequest(BaseModel):
    championship_id: int
    etapa: int
    data: str
    resultados_por_subdivisao: Dict[str, List[str]] # sub -> [piloto1, piloto2, ...]
    origem: str = "manual" # "manual" ou "blog"
    url_blog: Optional[str] = None
    auditoria_detalhes: Optional[Dict[str, Any]] = None # detalhes do blog se aplicável
    novos_apelidos: Optional[Dict[str, str]] = None # piloto -> novo apelido a salvar
    substituir_existentes: bool = False

@app.post("/api/stages/save-results")
def save_stage_results(req: SaveStageResultsRequest, admin: dict = Depends(require_admin)):
    conn = get_db()
    c = conn.cursor()
    
    c.execute("SELECT * FROM championships WHERE id = ?", (req.championship_id,))
    camp = c.fetchone()
    if not camp:
        conn.close()
        raise HTTPException(status_code=404, detail="Campeonato não encontrado.")
        
    cat_nome = camp["categoria"]
    resultados = json.loads(camp["resultados"])
    if not req.substituir_existentes and any(
        result["etapa"] == req.etapa
        for sub in req.resultados_por_subdivisao for result in resultados.get(sub, [])
    ):
        conn.close()
        raise HTTPException(status_code=409, detail="Esta etapa já tem resultados. Reabra a conferência e confirme a substituição para salvar.")
    fontes_blog = json.loads(camp["fontes_blog"])
    auditoria = json.loads(camp["auditoria"])
    datas = json.loads(camp["datas_das_etapas"])
    
    # Atualizar data da etapa no calendário se foi informada
    if req.etapa <= len(datas):
        datas[req.etapa - 1] = req.data
    elif req.etapa == len(datas) + 1:
        datas.append(req.data)
        
    # Salvar resultados de cada subdivisão
    for sub, ordem in req.resultados_por_subdivisao.items():
        if sub not in resultados:
            resultados[sub] = []
            
        # Remover resultado anterior da etapa se já existia
        resultados[sub] = [r for r in resultados[sub] if r["etapa"] != req.etapa]
        resultados[sub].append({
            "etapa": req.etapa,
            "data": req.data,
            "ordem_de_chegada": ordem
        })
        resultados[sub].sort(key=lambda x: x["etapa"])
        
        # Pilotos que aparecerem no resultado e não existirem no cadastro devem ser criados automaticamente
        for piloto_nome in ordem:
            c.execute("SELECT * FROM pilots WHERE nome = ?", (piloto_nome,))
            p_exist = c.fetchone()
            if not p_exist:
                provas = [{"categoria": cat_nome, "subdivisao": sub}]
                c.execute(
                    "INSERT INTO pilots (nome, apelidos, provas) VALUES (?, ?, ?)",
                    (piloto_nome, json.dumps([], ensure_ascii=False), json.dumps(provas, ensure_ascii=False))
                )
            else:
                provas = json.loads(p_exist["provas"])
                tem_cat = any(pr.get("categoria") == cat_nome for pr in provas)
                if not tem_cat:
                    provas.append({"categoria": cat_nome, "subdivisao": sub})
                    c.execute("UPDATE pilots SET provas = ? WHERE id = ?", (json.dumps(provas, ensure_ascii=False), p_exist["id"]))
                    
    # Salvar novos apelidos se houver
    if req.novos_apelidos:
        for p_nome, apelido in req.novos_apelidos.items():
            if apelido and apelido.strip():
                c.execute("SELECT id, apelidos FROM pilots WHERE nome = ?", (p_nome,))
                p_row = c.fetchone()
                if p_row:
                    aps = json.loads(p_row["apelidos"])
                    if apelido.strip() not in aps:
                        aps.append(apelido.strip())
                        c.execute("UPDATE pilots SET apelidos = ? WHERE id = ?", (json.dumps(aps, ensure_ascii=False), p_row["id"]))
                        
    # Registrar auditoria
    if req.url_blog:
        fontes_blog[str(req.etapa)] = req.url_blog
        
    audit_entry = {
        "url": req.url_blog or "",
        "origem": req.origem,
        "registrado_em": datetime.now().isoformat(),
        "editado_manualmente": (req.origem == "manual" and str(req.etapa) in fontes_blog),
        "por_subdivisao": req.auditoria_detalhes or {}
    }
    auditoria[str(req.etapa)] = audit_entry
    
    c.execute("""
        UPDATE championships SET
            resultados = ?,
            fontes_blog = ?,
            auditoria = ?,
            datas_das_etapas = ?
        WHERE id = ?
    """, (
        json.dumps(resultados, ensure_ascii=False),
        json.dumps(fontes_blog, ensure_ascii=False),
        json.dumps(auditoria, ensure_ascii=False),
        json.dumps(datas, ensure_ascii=False),
        req.championship_id
    ))
    
    conn.commit()
    conn.close()
    return {"ok": True, "etapa": req.etapa}

# Auditoria da Etapa
@app.get("/api/stages/audit/{championship_id}/{etapa}")
def get_stage_audit(championship_id: int, etapa: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT auditoria, fontes_blog FROM championships WHERE id = ?", (championship_id,))
    camp = c.fetchone()
    conn.close()
    if not camp:
        raise HTTPException(status_code=404, detail="Campeonato não encontrado.")
    auditoria = json.loads(camp["auditoria"])
    fontes = json.loads(camp["fontes_blog"])
    entry = auditoria.get(str(etapa), {})
    entry["url_fonte"] = fontes.get(str(etapa), "")
    return entry

# Reagendamento de Etapas (com ajuste automático das seguintes)
class RescheduleRequest(BaseModel):
    etapa: int
    nova_data: str
    reajustar_seguintes: bool = True

@app.post("/api/championships/{championship_id}/reschedule-stage")
def reschedule_stage(championship_id: int, req: RescheduleRequest, admin: dict = Depends(require_admin)):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM championships WHERE id = ?", (championship_id,))
    camp = c.fetchone()
    if not camp:
        conn.close()
        raise HTTPException(status_code=404, detail="Campeonato não encontrado.")
        
    datas = json.loads(camp["datas_das_etapas"])
    periodicidade = camp["periodicidade"].lower()
    
    deltas = {
        "diaria": timedelta(days=1),
        "semanal": timedelta(days=7),
        "quinzenal": timedelta(days=14),
        "mensal": timedelta(days=30)
    }
    step = deltas.get(periodicidade, timedelta(days=7))
    
    try:
        dt = datetime.strptime(req.nova_data, "%Y-%m-%d")
    except Exception:
        conn.close()
        raise HTTPException(status_code=400, detail="Formato de data inválido. Use AAAA-MM-DD.")
        
    idx = req.etapa - 1
    if 0 <= idx < len(datas):
        datas[idx] = req.nova_data
        if req.reajustar_seguintes:
            curr = dt
            for i in range(idx + 1, len(datas)):
                curr += step
                datas[i] = curr.strftime("%Y-%m-%d")
                
    c.execute("UPDATE championships SET datas_das_etapas = ? WHERE id = ?", (json.dumps(datas, ensure_ascii=False), championship_id))
    conn.commit()
    conn.close()
    return {"ok": True, "datas_das_etapas": datas}

# CRUD Campeonatos
class ChampionshipCreate(BaseModel):
    nome: str
    categoria: str
    inicio: str
    etapas: int
    descartes: int
    periodicidade: str
    tabela_pontuacao: str
    ultima_etapa_em_dobro: bool = True
    ranking_categoria: Optional[RankingCategory] = None
    regras_confirmadas: Optional[bool] = None
    situacao: Optional[Literal["em_andamento", "encerrado"]] = None
    incluir_no_ranking: Optional[bool] = None
    subdivisoes: List[Dict[str, Any]] # [{"subdivisao": "GT1", "tempo_de_corte": "5.9s", "sobem": 0, "rebaixados": 3}, ...]

@app.post("/api/championships")
def create_championship(req: ChampionshipCreate, admin: dict = Depends(require_admin)):
    ranking_category = identify_ranking_category(req.model_dump())
    if ranking_category is None:
        raise HTTPException(
            status_code=422,
            detail="Selecione o ranking: Fórmula 1, Magneto ou Brushless."
        )
    conn = get_db()
    c = conn.cursor()
    
    datas = generate_calendar(req.inicio, req.etapas, req.periodicidade)
    
    c.execute("""
        INSERT INTO championships (
            nome, categoria, inicio, etapas, descartes, periodicidade,
            ultima_etapa_em_dobro, tabela_pontuacao, datas_das_etapas,
            subdivisoes, resultados, fontes_blog, auditoria, ranking_categoria, regras_confirmadas,
            situacao, incluir_no_ranking
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        req.nome,
        req.categoria,
        req.inicio,
        req.etapas,
        req.descartes,
        req.periodicidade,
        1 if req.ultima_etapa_em_dobro else 0,
        req.tabela_pontuacao,
        json.dumps(datas, ensure_ascii=False),
        json.dumps(req.subdivisoes, ensure_ascii=False),
        json.dumps({}, ensure_ascii=False),
        json.dumps({}, ensure_ascii=False),
        json.dumps({}, ensure_ascii=False),
        ranking_category,
        0 if req.regras_confirmadas is False else 1,
        req.situacao or "em_andamento",
        0 if req.incluir_no_ranking is False else 1
    ))
    new_id = c.lastrowid
    conn.commit()
    conn.close()
    return {"ok": True, "id": new_id}

@app.put("/api/championships/{championship_id}")
def update_championship(championship_id: int, req: ChampionshipCreate, admin: dict = Depends(require_admin)):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM championships WHERE id = ?", (championship_id,))
    camp = c.fetchone()
    if not camp:
        conn.close()
        raise HTTPException(status_code=404, detail="Campeonato não encontrado.")
        
    datas = json.loads(camp["datas_das_etapas"])
    if len(datas) != req.etapas or camp["inicio"] != req.inicio or camp["periodicidade"] != req.periodicidade:
        datas = generate_calendar(req.inicio, req.etapas, req.periodicidade)
        
    c.execute("""
        UPDATE championships SET
            nome = ?, categoria = ?, inicio = ?, etapas = ?, descartes = ?,
            periodicidade = ?, ultima_etapa_em_dobro = ?, tabela_pontuacao = ?,
            datas_das_etapas = ?, subdivisoes = ?, ranking_categoria = ?, regras_confirmadas = ?,
            situacao = ?, incluir_no_ranking = ?
        WHERE id = ?
    """, (
        req.nome,
        req.categoria,
        req.inicio,
        req.etapas,
        req.descartes,
        req.periodicidade,
        1 if req.ultima_etapa_em_dobro else 0,
        req.tabela_pontuacao,
        json.dumps(datas, ensure_ascii=False),
        json.dumps(req.subdivisoes, ensure_ascii=False),
        req.ranking_categoria or camp["ranking_categoria"] or identify_ranking_category(req.model_dump()),
        camp["regras_confirmadas"] if req.regras_confirmadas is None else int(req.regras_confirmadas),
        req.situacao or camp["situacao"],
        camp["incluir_no_ranking"] if req.incluir_no_ranking is None else int(req.incluir_no_ranking),
        championship_id
    ))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.delete("/api/championships/{championship_id}")
def delete_championship(championship_id: int, admin: dict = Depends(require_admin)):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM championships WHERE id = ?", (championship_id,))
    conn.commit()
    conn.close()
    return {"ok": True}

# CRUD Pilotos
class PilotCreate(BaseModel):
    nome: str
    apelidos_no_blog: List[str] = []
    provas: List[Dict[str, str]] # [{"categoria": "Gran Turismo", "subdivisao": "GT1"}]

@app.post("/api/pilots")
def create_pilot(req: PilotCreate, admin: dict = Depends(require_admin)):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO pilots (nome, apelidos, provas) VALUES (?, ?, ?)",
        (req.nome.strip(), json.dumps(req.apelidos_no_blog, ensure_ascii=False), json.dumps(req.provas, ensure_ascii=False))
    )
    new_id = c.lastrowid
    conn.commit()
    conn.close()
    return {"ok": True, "id": new_id}

@app.put("/api/pilots/{pilot_id}")
def update_pilot(pilot_id: int, req: PilotCreate, admin: dict = Depends(require_admin)):
    nome = req.nome.strip()
    if not normalize_str(nome):
        raise HTTPException(status_code=422, detail="Informe um nome válido para o piloto.")
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM pilots WHERE id = ?", (pilot_id,))
        piloto = c.fetchone()
        if not piloto:
            raise HTTPException(status_code=404, detail="Piloto não encontrado.")
        apelidos = list(dict.fromkeys(a.strip() for a in req.apelidos_no_blog if a.strip()))
        if piloto["nome"] != nome and piloto["nome"] not in apelidos:
            apelidos.append(piloto["nome"])
        identidades = {normalize_str(n) for n in [nome, piloto["nome"], *apelidos]} - {""}
        c.execute("SELECT nome, apelidos FROM pilots WHERE id != ?", (pilot_id,))
        for outro in c.fetchall():
            nomes_outro = {normalize_str(n) for n in [outro["nome"], *json.loads(outro["apelidos"])]} - {""}
            if identidades & nomes_outro:
                raise HTTPException(
                    status_code=409,
                    detail=f"Nome ou apelido também pertence a {outro['nome']}. Confira os cadastros antes de unificar."
                )

        c.execute("SELECT id, nome, resultados, auditoria FROM championships")
        atualizacoes = []
        for camp in c.fetchall():
            resultados = json.loads(camp["resultados"])
            alterado = False
            presencas = set()
            for etapas in resultados.values():
                for etapa in etapas:
                    ordem = etapa["ordem_de_chegada"]
                    for i, nome_resultado in enumerate(ordem):
                        if normalize_str(nome_resultado) not in identidades:
                            continue
                        numero = etapa["etapa"]
                        if numero in presencas:
                            raise HTTPException(
                                status_code=409,
                                detail=f"{camp['nome']}, etapa {numero}: o piloto aparece mais de uma vez. Confira o resultado antes de unificar."
                            )
                        presencas.add(numero)
                        if nome_resultado != nome:
                            ordem[i] = nome
                            alterado = True
            if not alterado:
                continue
            auditoria = json.loads(camp["auditoria"])
            for registro in auditoria.values():
                por_subdivisao = registro.get("por_subdivisao", {})
                for entradas in por_subdivisao.values():
                    if not isinstance(entradas, list):
                        continue
                    for entrada in entradas:
                        if isinstance(entrada, dict) and normalize_str(entrada.get("piloto", "")) in identidades:
                            entrada["piloto"] = nome
            atualizacoes.append((json.dumps(resultados, ensure_ascii=False),
                                 json.dumps(auditoria, ensure_ascii=False), camp["id"]))
        for resultados, auditoria, camp_id in atualizacoes:
            c.execute("UPDATE championships SET resultados = ?, auditoria = ? WHERE id = ?",
                      (resultados, auditoria, camp_id))
        c.execute(
            "UPDATE pilots SET nome = ?, apelidos = ?, provas = ? WHERE id = ?",
            (nome, json.dumps(apelidos, ensure_ascii=False), json.dumps(req.provas, ensure_ascii=False), pilot_id)
        )
        conn.commit()
        return {"ok": True, "campeonatos_atualizados": len(atualizacoes)}
    finally:
        conn.close()

@app.delete("/api/pilots/{pilot_id}")
def delete_pilot(pilot_id: int, admin: dict = Depends(require_admin)):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM pilots WHERE id = ?", (pilot_id,))
    conn.commit()
    conn.close()
    return {"ok": True}

# CRUD Categorias
class CategoryCreate(BaseModel):
    nome: str
    subdivisoes: List[str] = ["GT1", "GT2", "GT3"]

@app.post("/api/categories")
def create_category(req: CategoryCreate, admin: dict = Depends(require_admin)):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO categories (nome, subdivisoes) VALUES (?, ?)",
        (req.nome.strip(), json.dumps(req.subdivisoes, ensure_ascii=False))
    )
    conn.commit()
    conn.close()
    return {"ok": True}

# CRUD Tabelas de Pontuação
class ScoringTableCreate(BaseModel):
    nome: str
    pontos_por_posicao: List[int]
    regra_alem_da_tabela: str = "posições acima do último valor: 0"

@app.post("/api/scoring-tables")
def create_scoring_table(req: ScoringTableCreate, admin: dict = Depends(require_admin)):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO scoring_tables (nome, pontos_por_posicao, regra_alem_da_tabela) VALUES (?, ?, ?)",
        (req.nome.strip(), json.dumps(req.pontos_por_posicao, ensure_ascii=False), req.regra_alem_da_tabela)
    )
    conn.commit()
    conn.close()
    return {"ok": True}

# Backup e Restauração
@app.get("/api/backup/export")
def export_backup(admin: dict = Depends(require_admin)):
    data = export_backup_json()
    return JSONResponse(
        content=data,
        headers={"Content-Disposition": f"attachment; filename=backup-slot-car-{datetime.now().strftime('%Y-%m-%d')}.json"}
    )

@app.post("/api/backup/restore")
def restore_backup(data: Dict[str, Any], admin: dict = Depends(require_admin)):
    if not data.get("categorias") or not data.get("campeonatos"):
        raise HTTPException(status_code=400, detail="Formato de arquivo de backup inválido.")
    restore_backup_json(data)
    return {"ok": True, "mensagem": "Backup restaurado com sucesso!"}
