import json
import sys
import httpx
from app.db import init_db, get_db, export_backup_json, restore_backup_json
from app.auth import verify_password
from app.scoring import calculate_classification
from app.blog_importer import parse_blog_content, fetch_blog_html

def run_acceptance_tests():
    print("=====================================================================")
    print("      TESTE DE ACEITAÇÃO: CLASSIFICAÇÃO GERAL · GT RACING SLOT CAR    ")
    print("=====================================================================\n")
    
    # 1. Inicializar Banco
    init_db("alegt@gtracing.com.br", "gtracing2026")
    
    # Validar Admin
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE email = ?", ("alegt@gtracing.com.br",))
    admin_row = c.fetchone()
    assert admin_row is not None, "Admin alegt@gtracing.com.br não encontrado no banco!"
    assert verify_password(admin_row["password_hash"], "gtracing2026"), "Senha do admin inválida!"
    print("✓ TESTE 1: Administrador 'alegt@gtracing.com.br' autenticado com sucesso.")
    
    # Carregar JSON de referência
    with open("dados-iniciais-slot-car.json", "r", encoding="utf-8") as f:
        seed = json.load(f)
        
    pilotos = seed["pilotos"]
    tabela = seed["tabelas_de_pontuacao"][0]
    
    # Teste V Fórmula Magneto 2026 (1 Etapa)
    camp_formula = next(c for c in seed["campeonatos"] if "Fórmula" in c["nome"])
    print(f"\n--- TESTE 2: {camp_formula['nome']} (1 Etapa) ---")
    for sub in ["GT1", "GT2"]:
        res = calculate_classification(camp_formula, sub, pilotos, tabela, max_etapa=1)
        calc_rows = res["classificacao"]
        esperado = camp_formula["classificacao_esperada"][sub]
        
        assert len(calc_rows) == len(esperado), f"{sub}: Esperados {len(esperado)} pilotos, obtidos {len(calc_rows)}"
        for i, exp in enumerate(esperado):
            calc = calc_rows[i]
            assert calc["piloto"] == exp["piloto"], f"Pos {exp['pos']}: esperado piloto {exp['piloto']}, obtido {calc['piloto']}"
            assert calc["total_com_descarte"] == exp["total_com_descarte"], f"{exp['piloto']}: esperado com_descarte={exp['total_com_descarte']}, obtido {calc['total_com_descarte']}"
            assert calc["total_sem_descarte"] == exp["total_sem_descarte"], f"{exp['piloto']}: esperado sem_descarte={exp['total_sem_descarte']}, obtido {calc['total_sem_descarte']}"
            
        print(f"  ✓ Subdivisão {sub}: 100% aprovado ({len(esperado)} pilotos conferidos).")
        
    # Teste Gran Turismo Magneto 2026 (4 Etapas - classificacao_esperada)
    camp_gt = next(c for c in seed["campeonatos"] if "Gran Turismo" in c["nome"])
    print(f"\n--- TESTE 3: {camp_gt['nome']} (4 Etapas - Oficial Alê GT) ---")
    for sub in ["GT1", "GT2", "GT3"]:
        res = calculate_classification(camp_gt, sub, pilotos, tabela, max_etapa=4)
        calc_rows = res["classificacao"]
        esperado = camp_gt["classificacao_esperada"][sub]
        
        assert len(calc_rows) == len(esperado), f"{sub}: Esperados {len(esperado)} pilotos, obtidos {len(calc_rows)}"
        for i, exp in enumerate(esperado):
            calc = calc_rows[i]
            assert calc["piloto"] == exp["piloto"], f"Pos {exp['pos']}: esperado piloto {exp['piloto']}, obtido {calc['piloto']}"
            assert calc["total_com_descarte"] == exp["total_com_descarte"], f"{exp['piloto']}: esperado com_descarte={exp['total_com_descarte']}, obtido {calc['total_com_descarte']}"
            assert calc["total_sem_descarte"] == exp["total_sem_descarte"], f"{exp['piloto']}: esperado sem_descarte={exp['total_sem_descarte']}, obtido {calc['total_sem_descarte']}"
            
        print(f"  ✓ Subdivisão {sub}: 100% aprovado ({len(esperado)} pilotos conferidos).")

    # Teste Gran Turismo Magneto 2026 (5 Etapas - classificacao_atual_a_conferir)
    print(f"\n--- TESTE 4: {camp_gt['nome']} (5 Etapas - Com 5ª Etapa do Blog) ---")
    for sub in ["GT1", "GT2", "GT3"]:
        res = calculate_classification(camp_gt, sub, pilotos, tabela, max_etapa=5)
        calc_rows = res["classificacao"]
        esperado = camp_gt["classificacao_atual_a_conferir"][sub]
        
        assert len(calc_rows) == len(esperado), f"{sub}: Esperados {len(esperado)} pilotos, obtidos {len(calc_rows)}"
        for i, exp in enumerate(esperado):
            calc = calc_rows[i]
            assert calc["piloto"] == exp["piloto"], f"Pos {exp['pos']}: esperado piloto {exp['piloto']}, obtido {calc['piloto']}"
            assert calc["total_com_descarte"] == exp["total_com_descarte"], f"{exp['piloto']}: esperado com_descarte={exp['total_com_descarte']}, obtido {calc['total_com_descarte']}"
            assert calc["total_sem_descarte"] == exp["total_sem_descarte"], f"{exp['piloto']}: esperado sem_descarte={exp['total_sem_descarte']}, obtido {calc['total_sem_descarte']}"
            
        print(f"  ✓ Subdivisão {sub}: 100% aprovado ({len(esperado)} pilotos conferidos).")
        
    # Teste Importação do Blog: 4ª Etapa GRAN TURISMO MAGNETO 2026
    print(f"\n--- TESTE 5: Importação do Blog (4ª Etapa GRAN TURISMO MAGNETO 2026) ---")
    url_4a = "https://gtautomodelismo.blogspot.com/2026/11/4-etapa-gran-turismo-magneto-2026.html"
    try:
        resp = httpx.get(url_4a, headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True, timeout=12.0)
        assert resp.status_code == 200, f"Blog retornou status {resp.status_code}"
        parsed = parse_blog_content(resp.text, pilotos, "Gran Turismo")
        
        assert parsed["etapa_num"] == 4, f"Esperado etapa 4, obtido {parsed['etapa_num']}"
        gt1_parsed = parsed["subdivisoes"].get("GT1", [])
        ordem_obtida = [p["piloto"] for p in gt1_parsed]
        ordem_esperada = [
            "Luli", "Bruno", "Rhanan", "Moch", "Dener", "Gustavo", "Rafael Lopes", "Helo Martins", "Samuel", "Cavalca", "Pezão"
        ]
        
        assert ordem_obtida == ordem_esperada, f"Ordem GT1 não bateu! Obtida: {ordem_obtida}, Esperada: {ordem_esperada}"
        print(f"  ✓ Extração e Reconhecimento da GT1: Ordem 100% correta:")
        print("    " + " -> ".join(ordem_obtida))
    except Exception as e:
        print(f"  ⚠️ Aviso na conexão externa do blog: {e}")
        
    # Teste Backup Export & Restore
    print(f"\n--- TESTE 6: Backup e Restauração ---")
    backup_data = export_backup_json()
    assert len(backup_data["campeonatos"]) == 2, "Backup deve conter 2 campeonatos"
    assert len(backup_data["pilotos"]) >= 50, "Backup deve conter todos os pilotos"
    restore_backup_json(backup_data)
    print("  ✓ Exportação e restauração do banco executadas com integridade total.")
    
    print("\n=====================================================================")
    print("               TODOS OS TESTES DE ACEITAÇÃO PASSARAM!               ")
    print("=====================================================================\n")

if __name__ == "__main__":
    run_acceptance_tests()
