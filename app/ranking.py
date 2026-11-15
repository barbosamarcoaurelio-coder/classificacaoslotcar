from datetime import date
from fractions import Fraction
from typing import Any, Dict, List, Literal, Optional

RankingCategory = Literal["formula1", "magneto", "brushless"]
RANKING_CATEGORIES = {
    "formula1": "Fórmula 1",
    "magneto": "Magneto",
    "brushless": "Brushless",
}
RANKING_START = date(2026, 8, 1)
DIVISION_WEIGHTS = {"GT1": 3, "GT2": 2, "GT3": 1}


def identify_ranking_category(championship: Dict[str, Any]) -> Optional[str]:
    explicit = championship.get("ranking_categoria")
    if explicit is not None:
        if explicit not in RANKING_CATEGORIES:
            raise ValueError("Categoria de ranking inválida.")
        return explicit
    if "brushless" in championship.get("categoria", "").casefold():
        return "brushless"
    try:
        weekday = date.fromisoformat(championship.get("inicio", "")).weekday()
    except ValueError:
        return None
    return {1: "formula1", 3: "magneto"}.get(weekday)


def calculate_rankings(
    championships: List[Dict[str, Any]], scoring_tables: List[Dict[str, Any]]
) -> Dict[str, Any]:
    tables = {table["nome"]: table["pontos_por_posicao"] for table in scoring_tables}
    totals: Dict[str, Dict[str, Any]] = {category: {} for category in RANKING_CATEGORIES}
    warnings = []
    for championship in championships:
        name = championship["nome"]
        if not championship.get("incluir_no_ranking", True):
            continue
        if not championship.get("regras_confirmadas", True):
            warnings.append(
                f"{name}: histórico salvo, mas fora do ranking até conferir as regras do campeonato."
            )
            continue
        category = championship.get("ranking_categoria")
        if category not in totals:
            warnings.append(
                f'{name}: defina o ranking em Campeonatos → Editar para incluir seus resultados.'
            )
            continue
        seen = set()
        for division, stages in championship["resultados"].items():
            for stage in stages:
                if stage.get("simulada"):
                    continue
                try:
                    stage_date = date.fromisoformat(stage["data"])
                except (KeyError, ValueError):
                    raise ValueError(f"{name}: informe uma data válida para cada resultado.")
                if stage_date < RANKING_START or not stage.get("ordem_de_chegada"):
                    continue
                if division not in DIVISION_WEIGHTS:
                    raise ValueError(f"{name}: subdivisão {division} sem peso de ranking.")
                stage_number = stage["etapa"]
                if not 1 <= stage_number <= championship["etapas"]:
                    raise ValueError(f"{name}: número de etapa inválido.")
                points = tables.get(championship["tabela_pontuacao"])
                if points is None or any(
                    type(value) is not int or not 0 <= value <= 30 for value in points
                ):
                    raise ValueError(f"{name}: a tabela do ranking deve ter pontos entre 0 e 30.")
                multiplier = (
                    2 if stage_number == championship["etapas"]
                    and championship["ultima_etapa_em_dobro"] else 1
                )
                for position, pilot in enumerate(stage["ordem_de_chegada"]):
                    participation = (stage_number, pilot)
                    if participation in seen:
                        raise ValueError(
                            f"{name}, etapa {stage_number}: {pilot} aparece mais de uma vez."
                        )
                    seen.add(participation)
                    row = totals[category].setdefault(
                        pilot, {"participacoes": 0, "pontos_ponderados": 0, "maximo": 0}
                    )
                    earned = points[position] if position < len(points) else 0
                    row["participacoes"] += 1
                    row["pontos_ponderados"] += earned * multiplier * DIVISION_WEIGHTS[division]
                    row["maximo"] += 30 * multiplier

    rankings = {}
    for category, pilots in totals.items():
        ordered = sorted(
            (
                {
                    "piloto": pilot,
                    "participacoes": row["participacoes"],
                    "indice": Fraction(100 * row["pontos_ponderados"], row["maximo"]),
                }
                for pilot, row in pilots.items()
            ),
            key=lambda row: (-row["indice"], row["participacoes"], row["piloto"]),
        )
        previous = None
        position = 0
        for index, row in enumerate(ordered, 1):
            tie_key = (row["indice"], row["participacoes"])
            if tie_key != previous:
                position = index
            previous = tie_key
            row["pos"] = position
            row["indice"] = float(row["indice"])
        rankings[category] = ordered
    return {"desde": RANKING_START.isoformat(), "rankings": rankings, "avisos": warnings}
