"""Traducción de errores de validación a algo que se pueda leer en pantalla.

Pydantic produce un texto excelente para quien escribe el código y pésimo para
quien usa la aplicación:

    el reglamento no es válido: 4 validation errors for RuleSet
    season.games_per_club_target
      Input should be less than or equal to 250 [type=less_than_equal,
      input_value=9999, input_type=int]
        For further information visit https://errors.pydantic.dev/2.14/v/...

Eso llegaba entero al aviso rojo del formulario, con la URL a pydantic.dev
incluida. Aquí se convierte en «La temporada → los partidos por club: no puede
pasar de 250», que es la misma información sin la jerga.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

#: Cómo se llama cada campo cuando hay que nombrarlo en un mensaje. La ruta
#: interna del modelo —`season.games_per_club_target`— no significa nada fuera
#: del código, y es justo lo que el usuario estaba viendo.
FIELD_LABELS: dict[str, str] = {
    "name": "el nombre",
    "kind": "el tipo de competición",
    "participation_modality": "la modalidad de participación",
    "scope": "el ámbito territorial",
    "level": "el nivel del ámbito",
    "place_keys": "los territorios elegidos",
    "entity_ids": "los territorios del gazetteer",
    "season": "la temporada",
    "games_per_club_target": "los partidos por club",
    "roster_size": "el tamaño de plantilla",
    "rest_days_weekday": "los días de descanso entre jornadas",
    "series_length": "la longitud de la serie",
    "start_date": "la fecha de inicio",
    "double_round": "la ida y vuelta",
    "playoffs": "la postemporada",
    "slots": "las plazas de postemporada",
    "format": "el formato",
    "round_lengths": "las rondas",
    "brackets": "las llaves",
    "feeds": "los pases entre rondas",
    "best_of": "los partidos de la serie",
    "games_per_pair": "los partidos por cruce",
    "qualifying_positions": "los puestos que clasifican",
    "generation": "la generación",
    "club_count": "el número de clubes",
    "seed": "la semilla",
    "markets": "los cupos por mercado",
    "structure": "la estructura",
    "divisions": "las divisiones",
    "groups": "los grupos",
    "admission": "los requisitos de admisión",
    "financial_regulations": "las normas económicas",
    "world_date": "la fecha del mundo",
    "currency": "la moneda",
    "master_seed": "la semilla del universo",
}

#: Los mensajes de Pydantic que más se ven, dichos en castellano. Lo que no
#: esté aquí se enseña tal cual: es mejor un mensaje en inglés que uno inventado.
_PATRONES: tuple[tuple[str, str], ...] = (
    ("Field required", "falta por rellenar"),
    ("Input should be a valid integer", "tiene que ser un número entero"),
    ("Input should be a valid number", "tiene que ser un número"),
    ("Input should be a valid list", "tiene que ser una lista"),
    ("Input should be a valid string", "tiene que ser texto"),
    ("Input should be a valid date", "tiene que ser una fecha"),
    ("Extra inputs are not permitted", "no es un campo que exista"),
    ("String should have at least", "es demasiado corto"),
    ("String should have at most", "es demasiado largo"),
    ("List should have at least", "necesita más elementos"),
    ("List should have at most", "tiene demasiados elementos"),
)


def human_field(location: tuple[Any, ...]) -> str:
    """La ruta de un error, dicha con las palabras del formulario."""
    partes = [
        str(pieza)
        for pieza in location
        if pieza not in ("body", "query", "path") and not isinstance(pieza, int)
    ]
    if not partes:
        return "los datos enviados"
    return " → ".join(FIELD_LABELS.get(parte, parte.replace("_", " ")) for parte in partes)


def human_message(raw: str) -> str:
    """El mensaje de Pydantic sin su andamiaje."""
    limpio = raw.removeprefix("Value error, ").removeprefix("Assertion failed, ")
    if limpio.startswith("Input should be less than or equal to "):
        return f"no puede pasar de {limpio.rsplit(' ', 1)[-1]}"
    if limpio.startswith("Input should be greater than or equal to "):
        return f"no puede bajar de {limpio.rsplit(' ', 1)[-1]}"
    if limpio.startswith("Input should be "):
        return f"tiene que ser {limpio.removeprefix('Input should be ')}"
    for patron, castellano in _PATRONES:
        if limpio.startswith(patron):
            return castellano
    # Muchas reglas del dominio explican el porqué técnico detrás de dos
    # puntos —«...al menos un lugar: `entity_ids` con entidades resueltas del
    # gazetteer...»—. Eso sirve a quien llama la API y estorba en pantalla: se
    # corta la cola técnica y se conserva la frase.
    if ": `" in limpio:
        cabeza = limpio.split(": `", 1)[0].strip()
        if len(cabeza) >= 12:
            return cabeza
    return limpio.replace("`", "«", 1).replace("`", "»", 1) if "`" in limpio else limpio


def explain(errors: list[dict[str, Any]], *, limit: int = 8) -> tuple[str, list[str]]:
    """Convierte errores de validación en `(titular, pistas)`.

    El titular dice **cuántos** problemas hay y las pistas dicen **cuáles**, una
    por línea. Ni una sola mención a tipos internos, rutas de modelo o URLs de
    la biblioteca.
    """
    pistas: list[str] = []
    for error in errors:
        campo = human_field(tuple(error.get("loc", ())))
        pistas.append(f"{campo}: {human_message(str(error.get('msg', 'valor no válido')))}")
    vistas: list[str] = []
    for pista in pistas:
        if pista not in vistas:
            vistas.append(pista)
    if len(vistas) == 1:
        # Con un solo problema no hace falta titular: el problema **es** el
        # titular, y así el aviso se lee de un vistazo.
        unico = vistas[0]
        return unico[0].upper() + unico[1:], []
    titular = f"Hay {len(vistas)} datos que no se pueden aceptar."
    return titular, vistas[:limit]


def explain_pydantic(exc: ValidationError, *, limit: int = 8) -> tuple[str, list[str]]:
    """Lo mismo, partiendo de la excepción de Pydantic."""
    return explain(list(exc.errors()), limit=limit)
