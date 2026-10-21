"""Aleatoriedad determinista derivada por contexto.

Ver `docs/adr/0003-rng-derivado-por-contexto.md`. La idea: no existe un flujo
global. Cada contexto (`("clubs", edition_id, slot)`) obtiene su propia semilla
derivada de la semilla maestra, de modo que añadir una opción a la interfaz o
simular un partido de más no desplaza el futuro de todo lo demás.
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Sequence

SeedPath = Sequence[object]


def derive_seed(master_seed: int, *path: object) -> int:
    """Deriva una semilla de 63 bits a partir de la maestra y una ruta.

    La ruta se serializa con separadores explícitos para que ("a", "bc") y
    ("ab", "c") no colisionen.
    """
    payload = b"|".join([str(int(master_seed)).encode()] + [str(p).encode() for p in path])
    digest = hashlib.blake2b(payload, digest_size=8).digest()
    # Se recorta a 63 bits con signo: la semilla se persiste en una columna
    # BIGINT y tanto PostgreSQL como SQLite usan enteros de 64 bits CON signo.
    # Sin la máscara, una semilla por encima de 2^63-1 revienta al guardarla.
    return int.from_bytes(digest, "big") & 0x7FFF_FFFF_FFFF_FFFF


def rng_for(master_seed: int, *path: object) -> random.Random:
    """Devuelve un generador independiente para el contexto dado."""
    return random.Random(derive_seed(master_seed, *path))


def weighted_choice(rng: random.Random, options: Sequence[tuple[object, float]]) -> object:
    """Elige una opción con pesos. Rechaza pesos no positivos en total."""
    total = sum(max(0.0, w) for _, w in options)
    if total <= 0:
        raise ValueError("weighted_choice necesita al menos un peso positivo")
    target = rng.random() * total
    acc = 0.0
    for value, weight in options:
        acc += max(0.0, weight)
        if target < acc:
            return value
    return options[-1][0]


def clamped_normal(
    rng: random.Random,
    mean: float,
    stdev: float,
    low: float = 0.0,
    high: float = 1.0,
) -> float:
    """Normal truncada por reintento acotado, con recorte final.

    Se usa para atributos: queremos una campana, no una uniforme, pero sin
    permitir que la cola salga del rango del atributo.
    """
    for _ in range(8):
        value = rng.gauss(mean, stdev)
        if low <= value <= high:
            return value
    return min(high, max(low, rng.gauss(mean, stdev)))
