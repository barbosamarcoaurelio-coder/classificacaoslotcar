import sqlite3
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from app.auth import hash_password

DB_PATH = os.environ.get("DB_PATH", "slotcar.db")
SEED_FILE = os.environ.get("SEED_FILE", "dados-iniciais-slot-car.json")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(admin_email: str = "alegt@gtracing.com.br", admin_password: str = "gtracing2026"):
    conn = get_db()
    c = conn.cursor()
    
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        is_admin INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    )
    """)
    
    c.execute("""
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT UNIQUE NOT NULL,
        subdivisoes TEXT NOT NULL
    )
    """)
    
    c.execute("""
    CREATE TABLE IF NOT EXISTS scoring_tables (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT UNIQUE NOT NULL,
        pontos_por_posicao TEXT NOT NULL,
        regra_alem_da_tabela TEXT
    )
    """)
    
    c.execute("""
    CREATE TABLE IF NOT EXISTS pilots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT UNIQUE NOT NULL,
        apelidos TEXT NOT NULL,
        provas TEXT NOT NULL
    )
    """)
    
    c.execute("""
    CREATE TABLE IF NOT EXISTS championships (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT UNIQUE NOT NULL,
        categoria TEXT NOT NULL,
        inicio TEXT NOT NULL,
        etapas INTEGER NOT NULL,
        descartes INTEGER NOT NULL,
        periodicidade TEXT NOT NULL,
        ultima_etapa_em_dobro INTEGER NOT NULL DEFAULT 1,
        tabela_pontuacao TEXT NOT NULL,
        datas_das_etapas TEXT NOT NULL,
        subdivisoes TEXT NOT NULL,
        resultados TEXT NOT NULL,
        fontes_blog TEXT NOT NULL,
        auditoria TEXT NOT NULL
    )
    """)
    
    conn.commit()
    
    # Criar ou atualizar admin
    c.execute("SELECT id FROM users WHERE email = ?", (admin_email,))
    if not c.fetchone():
        c.execute(
            "INSERT INTO users (email, password_hash, is_admin, created_at) VALUES (?, ?, 1, ?)",
            (admin_email, hash_password(admin_password), datetime.now().isoformat())
        )
        conn.commit()
        
    # Verificar se precisa rodar carga inicial (se categorias estiver vazio)
    c.execute("SELECT COUNT(*) as count FROM categories")
    if c.fetchone()["count"] == 0 and os.path.exists(SEED_FILE):
        seed_data(SEED_FILE, conn)
        
    conn.close()

def seed_data(filepath: str, conn: Optional[sqlite3.Connection] = None):
    should_close = False
    if conn is None:
        conn = get_db()
        should_close = True
        
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    c = conn.cursor()
    
    # Categorias
    for cat in data.get("categorias", []):
        c.execute(
            "INSERT OR REPLACE INTO categories (nome, subdivisoes) VALUES (?, ?)",
            (cat["nome"], json.dumps(cat.get("subdivisoes", ["GT1", "GT2", "GT3"]), ensure_ascii=False))
        )
        
    # Tabelas de pontuação
    for tab in data.get("tabelas_de_pontuacao", []):
        c.execute(
            "INSERT OR REPLACE INTO scoring_tables (nome, pontos_por_posicao, regra_alem_da_tabela) VALUES (?, ?, ?)",
            (tab["nome"], json.dumps(tab.get("pontos_por_posicao", []), ensure_ascii=False), tab.get("regra_alem_da_tabela", ""))
        )
        
    # Pilotos
    for pil in data.get("pilotos", []):
        c.execute(
            "INSERT OR REPLACE INTO pilots (nome, apelidos, provas) VALUES (?, ?, ?)",
            (pil["nome"], json.dumps(pil.get("apelidos_no_blog", []), ensure_ascii=False), json.dumps(pil.get("provas", []), ensure_ascii=False))
        )
        
    # Campeonatos
    for camp in data.get("campeonatos", []):
        c.execute("""
            INSERT OR REPLACE INTO championships (
                nome, categoria, inicio, etapas, descartes, periodicidade,
                ultima_etapa_em_dobro, tabela_pontuacao, datas_das_etapas,
                subdivisoes, resultados, fontes_blog, auditoria
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            camp["nome"],
            camp["categoria"],
            camp.get("inicio", ""),
            camp.get("etapas", 6),
            camp.get("descartes", 1),
            camp.get("periodicidade", "semanal"),
            1 if camp.get("ultima_etapa_em_dobro", True) else 0,
            camp.get("tabela_pontuacao", "Padrão GT Racing"),
            json.dumps(camp.get("datas_das_etapas", []), ensure_ascii=False),
            json.dumps(camp.get("subdivisoes", []), ensure_ascii=False),
            json.dumps(camp.get("resultados", {}), ensure_ascii=False),
            json.dumps(camp.get("fontes_blog", {}), ensure_ascii=False),
            json.dumps(camp.get("auditoria", {}), ensure_ascii=False),
        ))
        
    conn.commit()
    if should_close:
        conn.close()

def generate_calendar(inicio_str: str, etapas: int, periodicidade: str) -> List[str]:
    try:
        dt = datetime.strptime(inicio_str, "%Y-%m-%d")
    except Exception:
        dt = datetime.now()
        
    deltas = {
        "diaria": timedelta(days=1),
        "semanal": timedelta(days=7),
        "quinzenal": timedelta(days=14),
        "mensal": timedelta(days=30)
    }
    step = deltas.get(periodicidade.lower(), timedelta(days=7))
    
    datas = []
    curr = dt
    for _ in range(etapas):
        datas.append(curr.strftime("%Y-%m-%d"))
        curr += step
    return datas

def export_backup_json() -> Dict[str, Any]:
    conn = get_db()
    c = conn.cursor()
    
    c.execute("SELECT * FROM categories ORDER BY id ASC")
    cats = []
    for r in c.fetchall():
        cats.append({
            "nome": r["nome"],
            "subdivisoes": json.loads(r["subdivisoes"])
        })
        
    c.execute("SELECT * FROM scoring_tables ORDER BY id ASC")
    tabs = []
    for r in c.fetchall():
        tabs.append({
            "nome": r["nome"],
            "pontos_por_posicao": json.loads(r["pontos_por_posicao"]),
            "regra_alem_da_tabela": r["regra_alem_da_tabela"]
        })
        
    c.execute("SELECT * FROM pilots ORDER BY nome ASC")
    pils = []
    for r in c.fetchall():
        pils.append({
            "nome": r["nome"],
            "apelidos_no_blog": json.loads(r["apelidos"]),
            "provas": json.loads(r["provas"])
        })
        
    c.execute("SELECT * FROM championships ORDER BY id ASC")
    camps = []
    for r in c.fetchall():
        camps.append({
            "nome": r["nome"],
            "categoria": r["categoria"],
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
        "gerado_em": datetime.now().strftime("%Y-%m-%d"),
        "observacoes": [
            "Backup oficial gerado pelo sistema Classificação Geral · GT Racing Slot Car."
        ],
        "categorias": cats,
        "tabelas_de_pontuacao": tabs,
        "pilotos": pils,
        "campeonatos": camps
    }

def restore_backup_json(data: Dict[str, Any]):
    conn = get_db()
    c = conn.cursor()
    
    # Limpar e recarregar
    c.execute("DELETE FROM categories")
    c.execute("DELETE FROM scoring_tables")
    c.execute("DELETE FROM pilots")
    c.execute("DELETE FROM championships")
    try:
        c.execute("DELETE FROM sqlite_sequence")
    except Exception:
        pass
    
    # Categorias
    for cat in data.get("categorias", []):
        c.execute(
            "INSERT INTO categories (nome, subdivisoes) VALUES (?, ?)",
            (cat["nome"], json.dumps(cat.get("subdivisoes", ["GT1", "GT2", "GT3"]), ensure_ascii=False))
        )
        
    # Tabelas
    for tab in data.get("tabelas_de_pontuacao", []):
        c.execute(
            "INSERT INTO scoring_tables (nome, pontos_por_posicao, regra_alem_da_tabela) VALUES (?, ?, ?)",
            (tab["nome"], json.dumps(tab.get("pontos_por_posicao", []), ensure_ascii=False), tab.get("regra_alem_da_tabela", ""))
        )
        
    # Pilotos
    for pil in data.get("pilotos", []):
        c.execute(
            "INSERT INTO pilots (nome, apelidos, provas) VALUES (?, ?, ?)",
            (pil["nome"], json.dumps(pil.get("apelidos_no_blog", []), ensure_ascii=False), json.dumps(pil.get("provas", []), ensure_ascii=False))
        )
        
    # Campeonatos
    for camp in data.get("campeonatos", []):
        c.execute("""
            INSERT INTO championships (
                nome, categoria, inicio, etapas, descartes, periodicidade,
                ultima_etapa_em_dobro, tabela_pontuacao, datas_das_etapas,
                subdivisoes, resultados, fontes_blog, auditoria
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            camp["nome"],
            camp["categoria"],
            camp.get("inicio", ""),
            camp.get("etapas", 6),
            camp.get("descartes", 1),
            camp.get("periodicidade", "semanal"),
            1 if camp.get("ultima_etapa_em_dobro", True) else 0,
            camp.get("tabela_pontuacao", "Padrão GT Racing"),
            json.dumps(camp.get("datas_das_etapas", []), ensure_ascii=False),
            json.dumps(camp.get("subdivisoes", []), ensure_ascii=False),
            json.dumps(camp.get("resultados", {}), ensure_ascii=False),
            json.dumps(camp.get("fontes_blog", {}), ensure_ascii=False),
            json.dumps(camp.get("auditoria", {}), ensure_ascii=False),
        ))
        
    conn.commit()
    conn.close()
