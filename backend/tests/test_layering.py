"""ADR 0001 — la regla de dependencias se verifica, no se confía.

`simulation` es un paquete puro: si alguien importa FastAPI, el ORM o `app`
dentro del motor, esta prueba falla.
"""

from __future__ import annotations

import ast
from pathlib import Path

SIMULATION = Path(__file__).resolve().parents[2] / "simulation"
PROHIBIDO = ("fastapi", "sqlalchemy", "alembic", "app", "starlette", "uvicorn", "psycopg")


def _imports_of(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    return found


def test_el_motor_no_importa_infraestructura():
    infracciones: list[str] = []
    for path in SIMULATION.rglob("*.py"):
        if "tests" in path.parts:
            continue
        for module in _imports_of(path):
            if module in PROHIBIDO:
                infracciones.append(f"{path.relative_to(SIMULATION.parent)} importa {module}")
    assert not infracciones, "el motor dejó de ser un paquete puro:\n" + "\n".join(infracciones)


def test_el_motor_se_puede_usar_sin_servidor_ni_base_de_datos():
    """Importar y ejecutar el motor no debe requerir nada más."""
    import subprocess
    import sys

    script = (
        f"import sys; sys.path.insert(0, {str(SIMULATION.parent)!r});"
        "from datetime import date;"
        "from simulation.competitions.ruleset import RuleSet;"
        "from simulation.generation.world import generate_competition_world;"
        "from simulation.geography.provider import FixtureGeographyProvider;"
        "rs = RuleSet.model_validate({'name':'Prueba de aislamiento','kind':'municipal_league',"
        "'scope':{'level':'municipal','country_code':'MX','place_keys':['MX-CJS']},"
        "'season':{'games_per_club_target':12},'generation':{'club_count':4,'seed':1}});"
        "w = generate_competition_world(FixtureGeographyProvider().load(), rs, 1, 'e', date(2042,1,1));"
        "print(len(w.clubs), len(w.schedule.games))"
    )
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    # 4 clubes × 12 partidos / 2 = 24 encuentros.
    assert result.stdout.strip() == "4 24"
