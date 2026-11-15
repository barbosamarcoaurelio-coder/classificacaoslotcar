import random
import math
from typing import Dict, List, Any, Optional

def calculate_projection_probabilities(
    linhas: List[Dict[str, Any]],
    total_etapas: int,
    etapas_disputadas: int,
    descartes_config: int,
    dobro_ultima: bool,
    pontos_por_pos: List[int],
    qtd_sobem: int,
    qtd_rebaixados: int,
    n_sim: int = 1000
) -> tuple:
    """
    Projeta o % de chance de cada piloto subir de divisão (acesso) e
    cair de divisão (rebaixamento) utilizando simulação de Monte Carlo.
    """
    total_pilotos = len(linhas)
    pilotos_lista = [l["piloto"] for l in linhas]

    etapas_restantes = total_etapas - etapas_disputadas
    if etapas_restantes <= 0:
        probs_sub = {}
        probs_que = {}
        for l in linhas:
            probs_sub[l["piloto"]] = 100.0 if (qtd_sobem > 0 and l["pos"] <= qtd_sobem) else 0.0
            probs_que[l["piloto"]] = 100.0 if (qtd_rebaixados > 0 and l["pos"] > (total_pilotos - qtd_rebaixados)) else 0.0
        return probs_sub, probs_que

    perfis = {}
    for l in linhas:
        piloto = l["piloto"]
        historico_pts = [
            ep["pontos"] for ep in l["etapas"].values() 
            if ep.get("realizada") and not ep.get("simulada", False) and ep.get("pontos") is not None
        ]
        pts_presentes = [p for p in historico_pts if p > 0]
        presencas = len(pts_presentes)
        
        taxa_presenca = max(0.40, presencas / max(1, etapas_disputadas))
        if pts_presentes:
            media_pts = sum(pts_presentes) / len(pts_presentes)
            variance = sum((p - media_pts) ** 2 for p in pts_presentes) / len(pts_presentes)
            desvio = max(2.5, math.sqrt(variance))
        else:
            media_pts = 10.0
            desvio = 3.5
            
        perfis[piloto] = {
            "historico": list(historico_pts),
            "media": media_pts,
            "desvio": desvio,
            "taxa_presenca": taxa_presenca
        }

    descartes_final = min(descartes_config, max(0, total_etapas - 1))
    promotion_counts = {p: 0 for p in pilotos_lista}
    relegation_counts = {p: 0 for p in pilotos_lista}

    for _ in range(n_sim):
        pontuacoes_finais_sim = {p: list(perfis[p]["historico"]) for p in pilotos_lista}
        
        for e in range(etapas_disputadas + 1, total_etapas + 1):
            is_ultima = (e == total_etapas and dobro_ultima)
            multiplicador = 2 if is_ultima else 1
            
            scores_etapa = []
            for p in pilotos_lista:
                prof = perfis[p]
                if random.random() < prof["taxa_presenca"]:
                    performance = random.gauss(prof["media"], prof["desvio"])
                else:
                    performance = -9999.0
                scores_etapa.append((p, performance))
                
            scores_etapa.sort(key=lambda x: x[1], reverse=True)
            
            for pos_idx, (p, perf) in enumerate(scores_etapa):
                if perf > -9000.0:
                    pts = (pontos_por_pos[pos_idx] if pos_idx < len(pontos_por_pos) else 0) * multiplicador
                else:
                    pts = 0
                pontuacoes_finais_sim[p].append(pts)
                
        linhas_sim = []
        for p in pilotos_lista:
            all_pts = pontuacoes_finais_sim[p]
            tot_sem = sum(all_pts)
            pts_ordenados = sorted(all_pts)
            descartados = pts_ordenados[:descartes_final]
            tot_com = tot_sem - sum(descartados)
            linhas_sim.append({"piloto": p, "com": tot_com, "sem": tot_sem})
            
        linhas_sim.sort(key=lambda x: (-x["com"], -x["sem"], x["piloto"]))
        
        for rank, item in enumerate(linhas_sim, 1):
            if qtd_sobem > 0 and rank <= qtd_sobem:
                promotion_counts[item["piloto"]] += 1
            if qtd_rebaixados > 0 and rank > (total_pilotos - qtd_rebaixados):
                relegation_counts[item["piloto"]] += 1
                
    probs_sub = {p: round((promotion_counts[p] / n_sim) * 100.0, 1) for p in pilotos_lista}
    probs_que = {p: round((relegation_counts[p] / n_sim) * 100.0, 1) for p in pilotos_lista}
    return probs_sub, probs_que

def calculate_classification(
    camp: Dict[str, Any],
    subdivisao_nome: str,
    pontuacao_tabela: Dict[str, Any],
    max_etapa: Optional[int] = None,
    simulacao: bool = False,
    seed: Optional[int] = None
) -> Dict[str, Any]:
    """
    Calcula a classificação oficial de um campeonato e subdivisão.
    Regras:
    - N = mínimo(descartes do campeonato, etapas disputadas - 1). Ausência conta 0.
    - Na última etapa os pontos valem em dobro (se ultima_etapa_em_dobro == True).
    - Ordenação: maior total com descarte. Desempate: maior total sem descarte, depois nome.
    - Participam somente pilotos com resultado neste campeonato e subdivisão.
    """
    descartes_config = camp.get("descartes", 0)
    total_etapas_campeonato = camp.get("etapas", 1)
    dobro_ultima = camp.get("ultima_etapa_em_dobro", True)
    
    resultados_sub = list(camp.get("resultados", {}).get(subdivisao_nome, []))
    if max_etapa is not None:
        resultados_sub = [r for r in resultados_sub if r["etapa"] <= max_etapa]
        
    # Ordenar por número da etapa
    resultados_sub.sort(key=lambda r: r["etapa"])
    pilotos_na_sub = {
        piloto
        for resultado in resultados_sub
        for piloto in resultado.get("ordem_de_chegada", [])
    }
    
    # Se for simulação, preencher as etapas restantes até total_etapas_campeonato
    etapas_existentes = set(r["etapa"] for r in resultados_sub)
    if simulacao and len(resultados_sub) < total_etapas_campeonato:
        if seed is not None:
            random.seed(seed)
        lista_pilotos_sim = sorted(pilotos_na_sub)
        datas = camp.get("datas_das_etapas", [])
        
        for e in range(1, total_etapas_campeonato + 1):
            if e not in etapas_existentes:
                data_etapa = datas[e - 1] if len(datas) >= e else f"Etapa {e}"
                ordem_sorteada = list(lista_pilotos_sim)
                random.shuffle(ordem_sorteada)
                resultados_sub.append({
                    "etapa": e,
                    "data": data_etapa,
                    "ordem_de_chegada": ordem_sorteada,
                    "simulada": True
                })
        resultados_sub.sort(key=lambda r: r["etapa"])

    num_etapas_disputadas = len(resultados_sub)
    num_descartes = min(descartes_config, max(0, num_etapas_disputadas - 1))
    
    pontos_por_pos = pontuacao_tabela.get("pontos_por_posicao", [30, 28, 26, 25, 24, 23, 22, 21, 20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9])
    
    # Configuração de sobem/rebaixados da subdivisão
    sub_config = next((s for s in camp.get("subdivisoes", []) if s.get("subdivisao") == subdivisao_nome), {})
    qtd_sobem = sub_config.get("sobem", 0)
    qtd_rebaixados = sub_config.get("rebaixados", 0)
    tempo_de_corte = sub_config.get("tempo_de_corte")
    
    # Dicionário de resultados indexado por número de etapa
    res_por_etapa = {r["etapa"]: r for r in resultados_sub}
    
    linhas = []
    for piloto in pilotos_na_sub:
        etapas_pontos = {}
        valores_pontos = []
        
        for e_num in range(1, total_etapas_campeonato + 1):
            is_ultima = (e_num == total_etapas_campeonato and dobro_ultima)
            multiplicador = 2 if is_ultima else 1
            
            if e_num in res_por_etapa:
                r = res_por_etapa[e_num]
                ordem = r.get("ordem_de_chegada", [])
                
                if piloto in ordem:
                    pos = ordem.index(piloto) + 1
                    if pos <= len(pontos_por_pos):
                        pts = pontos_por_pos[pos - 1] * multiplicador
                    else:
                        pts = 0
                    presente = True
                else:
                    pts = 0
                    presente = False
                    pos = None
                    
                etapas_pontos[e_num] = {
                    "etapa": e_num,
                    "realizada": True,
                    "presente": presente,
                    "posicao": pos,
                    "pontos": pts,
                    "descartada": False,
                    "is_ultima": is_ultima,
                    "simulada": r.get("simulada", False)
                }
                valores_pontos.append((pts, e_num))
            else:
                # Etapa faltante (ainda não disputada)
                etapas_pontos[e_num] = {
                    "etapa": e_num,
                    "realizada": False,
                    "presente": False,
                    "posicao": None,
                    "pontos": None,
                    "descartada": False,
                    "is_ultima": is_ultima,
                    "simulada": False
                }
            
        total_sem_descarte = sum(ep["pontos"] for ep in etapas_pontos.values() if ep.get("realizada") and ep["pontos"] is not None)
        
        # Descartes: menores pontuações das etapas realizadas
        valores_ordenados = sorted(valores_pontos, key=lambda x: (x[0], x[1]))
        descartados = valores_ordenados[:num_descartes]
        descartados_ids = [x[1] for x in descartados]
        
        for etapa_id in descartados_ids:
            etapas_pontos[etapa_id]["descartada"] = True
            
        total_com_descarte = sum(
            ep["pontos"] for eid, ep in etapas_pontos.items() if ep.get("realizada") and ep["pontos"] is not None and not ep["descartada"]
        )
        
        linhas.append({
            "piloto": piloto,
            "total_com_descarte": total_com_descarte,
            "total_sem_descarte": total_sem_descarte,
            "etapas": etapas_pontos
        })
        
    # Ordenação oficial: 1º total com descarte DESC, 2º total sem descarte DESC, 3º nome ASC
    linhas.sort(key=lambda x: (-x["total_com_descarte"], -x["total_sem_descarte"], x["piloto"]))
    
    total_pilotos = len(linhas)
    for i, linha in enumerate(linhas, 1):
        linha["pos"] = i
        # Status de acesso/rebaixamento
        if qtd_sobem > 0 and i <= qtd_sobem:
            linha["status"] = "sobe"
        elif qtd_rebaixados > 0 and i > (total_pilotos - qtd_rebaixados):
            linha["status"] = "rebaixa"
        else:
            linha["status"] = "normal"

    # Calcular projeções estatísticas (% de chance de subir e cair)
    probs_subir, probs_queda = calculate_projection_probabilities(
        linhas=linhas,
        total_etapas=total_etapas_campeonato,
        etapas_disputadas=num_etapas_disputadas,
        descartes_config=descartes_config,
        dobro_ultima=dobro_ultima,
        pontos_por_pos=pontos_por_pos,
        qtd_sobem=qtd_sobem,
        qtd_rebaixados=qtd_rebaixados
    )
    for l in linhas:
        l["chance_acesso"] = probs_subir.get(l["piloto"], 0.0)
        l["chance_rebaixamento"] = probs_queda.get(l["piloto"], 0.0)
            
    lista_etapas_info = []
    datas_camp = camp.get("datas_das_etapas", [])
    for e_num in range(1, total_etapas_campeonato + 1):
        dt_str = datas_camp[e_num - 1] if len(datas_camp) >= e_num else ""
        r_item = res_por_etapa.get(e_num)
        lista_etapas_info.append({
            "etapa": e_num,
            "data": dt_str,
            "realizada": (e_num in res_por_etapa),
            "is_ultima": (e_num == total_etapas_campeonato and dobro_ultima),
            "simulada": r_item.get("simulada", False) if r_item else False
        })
        
    return {
        "campeonato": camp.get("nome"),
        "categoria": camp.get("categoria"),
        "subdivisao": subdivisao_nome,
        "tempo_de_corte": tempo_de_corte,
        "sobem": qtd_sobem,
        "rebaixados": qtd_rebaixados,
        "descartes_aplicados": num_descartes,
        "descartes_configurados": descartes_config,
        "etapas_disputadas": num_etapas_disputadas,
        "total_etapas": total_etapas_campeonato,
        "simulacao": simulacao,
        "etapas_info": lista_etapas_info,
        "classificacao": linhas
    }

def generate_export_html(classificacao_dict: Dict[str, Any]) -> str:
    """
    Gera um HTML autônomo e estilizado para exportação da classificação.
    """
    info = classificacao_dict
    linhas = info.get("classificacao", [])
    etapas_info = info.get("etapas_info", [])
    
    etapas_th = "".join(
        f'<th style="padding:8px 4px;text-align:center;border:1px solid #ddd;font-size:12px;">E{e["etapa"]}{" ×2" if e["is_ultima"] else ""}</th>'
        for e in etapas_info
    )
    
    rows_html = []
    for l in linhas:
        pos = l["pos"]
        piloto = l["piloto"]
        com_desc = l["total_com_descarte"]
        sem_desc = l["total_sem_descarte"]
        chance_subir = l.get("chance_acesso", 0.0)
        chance_queda = l.get("chance_rebaixamento", 0.0)
        status = l.get("status", "normal")
        
        # Cores de destaque
        row_style = "border-bottom:1px solid #e0e0e0;"
        text_color = "inherit"
        badge_icon = ""
        
        if pos == 1:
            row_style += "background-color:#111111;color:#FFCE00;font-weight:bold;"
            text_color = "#FFCE00"
        elif pos == 2:
            row_style += "background-color:#DD0000;color:#ffffff;font-weight:bold;"
            text_color = "#ffffff"
        elif pos == 3:
            row_style += "background-color:#FFCE00;color:#000000;font-weight:bold;"
            text_color = "#000000"
        elif status == "sobe":
            row_style += "background-color:#FFF9C4;color:#333333;"
            badge_icon = ' <span style="color:#F57F17;font-weight:bold;">↑</span>'
        elif status == "rebaixa":
            row_style += "background-color:#FFEBEE;color:#B71C1C;"
            badge_icon = ' <span style="color:#D32F2F;font-weight:bold;">↓</span>'
            
        # Cor do % Subir
        if chance_subir >= 60.0:
            subir_color = "#2E7D32;font-weight:bold;"
        elif chance_subir >= 25.0:
            subir_color = "#1565C0;font-weight:bold;"
        elif chance_subir > 0.0:
            subir_color = "#2E7D32;"
        else:
            subir_color = "opacity:0.45;"

        # Cor do % Queda
        if chance_queda >= 60.0:
            queda_color = "#D32F2F;font-weight:bold;"
        elif chance_queda >= 25.0:
            queda_color = "#E65100;font-weight:bold;"
        elif chance_queda > 0.0:
            queda_color = "#D32F2F;"
        else:
            queda_color = "opacity:0.45;"
            
        cells_etapas = []
        for e in etapas_info:
            eid = e["etapa"]
            ep = l["etapas"].get(eid, {})
            if not ep.get("realizada", False):
                val_str = '<span style="opacity:0.35;">-</span>'
            elif not ep.get("presente", False):
                if ep.get("descartada", False):
                    val_str = '<s style="opacity:0.5;">0</s>'
                else:
                    val_str = '<span style="opacity:0.75;">0</span>'
            else:
                pts = ep.get("pontos", 0)
                pos_etapa = ep.get("posicao")
                pos_str = f'<small style="font-size:10px;opacity:0.8;">({pos_etapa}º)</small>' if pos_etapa else ''
                if ep.get("descartada", False):
                    val_str = f'<s style="opacity:0.5;">{pts}</s> {pos_str}'
                else:
                    val_str = f'<strong>{pts}</strong> {pos_str}'
            cells_etapas.append(f'<td style="padding:8px 4px;text-align:center;border:1px solid #ddd;font-size:12px;">{val_str}</td>')
            
        tds_e = "".join(cells_etapas)
        rows_html.append(f'''
        <tr style="{row_style}">
            <td style="padding:8px;text-align:center;font-weight:bold;">{pos}º</td>
            <td style="padding:8px;font-weight:600;color:{text_color};">{piloto}{badge_icon}</td>
            <td style="padding:8px 4px;text-align:center;font-size:13px;font-weight:bold;width:78px;min-width:78px;max-width:78px;">{sem_desc}</td>
            <td style="padding:8px 4px;text-align:center;font-size:14px;font-weight:900;width:78px;min-width:78px;max-width:78px;background:rgba(0,0,0,0.06);">{com_desc}</td>
            <td style="padding:8px 4px;text-align:center;font-size:12px;color:{subir_color};width:66px;">{chance_subir}%</td>
            <td style="padding:8px 4px;text-align:center;font-size:12px;color:{queda_color};width:66px;">{chance_queda}%</td>
            {tds_e}
        </tr>
        ''')
        
    tbody_content = "\n".join(rows_html)
    
    html = f'''<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{info["campeonato"]} - {info["subdivisao"]} - Classificação</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 0; padding: 16px; background: #f8f9fa; color: #212529; }}
  .container {{ max-width: 960px; margin: 0 auto; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
  .flag-stripe {{ display: flex; height: 6px; }}
  .stripe-black {{ flex: 1; background: #000000; }}
  .stripe-red {{ flex: 1; background: #DD0000; }}
  .stripe-yellow {{ flex: 1; background: #FFCE00; }}
  .header {{ padding: 18px 20px; background: #111; color: #fff; }}
  .header h1 {{ margin: 0 0 6px 0; font-size: 20px; color: #FFCE00; }}
  .header h2 {{ margin: 0; font-size: 14px; font-weight: normal; color: #ccc; }}
  .table-responsive {{ overflow-x: auto; padding: 12px 16px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ background: #212529; color: #fff; }}
  .legend {{ padding: 16px; font-size: 12px; color: #666; border-top: 1px solid #eee; display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }}
  .legend-item {{ display: inline-flex; align-items: center; gap: 6px; }}
  .box {{ width: 14px; height: 14px; border-radius: 3px; display: inline-block; }}
</style>
</head>
<body>
<div class="container">
  <div class="flag-stripe">
    <div class="stripe-black"></div>
    <div class="stripe-red"></div>
    <div class="stripe-yellow"></div>
  </div>
  <div class="header">
    <h1>{info["campeonato"]} · Subdivisão {info["subdivisao"]}</h1>
    <h2>Classificação Geral · GT Racing Slot Car | {info["etapas_disputadas"]}/{info["total_etapas"]} etapas disputadas ({info["descartes_aplicados"]} descarte(s) aplicado(s))</h2>
    {f'<div style="margin-top:6px;font-size:12px;color:#FFCE00;">Tempo de corte: {info["tempo_de_corte"]}</div>' if info.get("tempo_de_corte") else ''}
  </div>
  <div class="table-responsive">
    <table>
      <thead>
        <tr>
          <th style="padding:10px 8px;text-align:center;border:1px solid #444;width:40px;">Pos</th>
          <th style="padding:10px 8px;text-align:left;border:1px solid #444;">Piloto</th>
          <th style="padding:10px 4px;text-align:center;border:1px solid #444;width:78px;min-width:78px;max-width:78px;">Total</th>
          <th style="padding:10px 4px;text-align:center;border:1px solid #444;width:78px;min-width:78px;max-width:78px;background:#2a2a2a;color:#FFCE00;line-height:1.2;">Total<br>c/ Descarte</th>
          <th style="padding:10px 4px;text-align:center;border:1px solid #444;width:66px;color:#81c784;">% Subir</th>
          <th style="padding:10px 4px;text-align:center;border:1px solid #444;width:66px;color:#ff9800;">% Queda</th>
          {etapas_th}
        </tr>
      </thead>
      <tbody>
        {tbody_content}
      </tbody>
    </table>
  </div>
  <div class="legend">
    <span class="legend-item"><span class="box" style="background:#111;"></span> 1º Lugar</span>
    <span class="legend-item"><span class="box" style="background:#DD0000;"></span> 2º Lugar</span>
    <span class="legend-item"><span class="box" style="background:#FFCE00;"></span> 3º Lugar</span>
    {f'<span class="legend-item"><span class="box" style="background:#FFF9C4;border:1px solid #F57F17;"></span> Zona de Acesso (↑ {info["sobem"]})</span>' if info.get("sobem", 0) > 0 else ''}
    {f'<span class="legend-item"><span class="box" style="background:#FFEBEE;border:1px solid #D32F2F;"></span> Zona de Rebaixamento (↓ {info["rebaixados"]})</span>' if info.get("rebaixados", 0) > 0 else ''}
    <span class="legend-item">% Subir / % Queda: Projeções de acesso e rebaixamento via Monte Carlo</span>
    <span class="legend-item"><s>Nº</s> = Etapa Descartada</span>
    <span class="legend-item">0 = Não correu (0 pts)</span>
    <span class="legend-item">×2 = Pontuação em dobro na última etapa</span>
  </div>
  <div class="flag-stripe">
    <div class="stripe-black"></div>
    <div class="stripe-red"></div>
    <div class="stripe-yellow"></div>
  </div>
</div>
</body>
</html>'''
    return html
    return html
