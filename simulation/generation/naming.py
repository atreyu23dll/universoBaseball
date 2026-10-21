"""Generación de nombres de clubes y personas, determinista y sin repetir."""

from __future__ import annotations

import random

from simulation.generation.lexicon import (
    CLUB_PREFIXES,
    CLUB_SUFFIX_INSTITUTIONAL,
    COUNTRY_LOCALE,
    NAME_POOLS,
    NICKNAMES_CIVIC,
    NICKNAMES_FAUNA,
    NICKNAMES_GEO,
    NICKNAMES_TRADE,
)

PROCEDURE_VERSION = "naming/1.0.0"

_NICK_BY_TYPE = {
    "community": NICKNAMES_FAUNA + NICKNAMES_CIVIC,
    "corporate": NICKNAMES_TRADE + NICKNAMES_FAUNA,
    "university": NICKNAMES_FAUNA + NICKNAMES_CIVIC,
    "municipal": NICKNAMES_GEO + NICKNAMES_CIVIC,
    "private": NICKNAMES_FAUNA + NICKNAMES_GEO,
    "franchise": NICKNAMES_FAUNA + NICKNAMES_GEO + NICKNAMES_TRADE,
}


class NameRegistry:
    """Evita colisiones dentro de un universo.

    Reparte sin repetir mientras queden opciones; si el pool se agota añade un
    discriminante, en vez de fallar o de entregar dos clubes idénticos.
    """

    def __init__(self) -> None:
        self._used: set[str] = set()

    def claim(self, candidate: str) -> str:
        if candidate not in self._used:
            self._used.add(candidate)
            return candidate
        suffix = 2
        while f"{candidate} {suffix}" in self._used:
            suffix += 1
        taken = f"{candidate} {suffix}"
        self._used.add(taken)
        return taken

    def is_free(self, candidate: str) -> bool:
        return candidate not in self._used


def club_name(
    rng: random.Random,
    registry: NameRegistry,
    place_name: str,
    institutional_type: str,
) -> tuple[str, str, str]:
    """Devuelve (nombre completo, apodo, nombre corto)."""
    nicknames = _NICK_BY_TYPE.get(institutional_type, NICKNAMES_FAUNA)
    options = [n for n in nicknames if registry.is_free(f"{n}::{place_name}")]
    nickname = rng.choice(options or nicknames)
    registry.claim(f"{nickname}::{place_name}")

    shape = rng.random()
    if shape < 0.45:
        full = f"{nickname} de {place_name}"
    elif shape < 0.75:
        full = f"{rng.choice(CLUB_PREFIXES)} {nickname}"
    else:
        suffixes = CLUB_SUFFIX_INSTITUTIONAL.get(institutional_type) or []
        tail = f" {rng.choice(suffixes)}" if suffixes and rng.random() < 0.6 else ""
        full = f"{nickname} {place_name}{tail}"

    return registry.claim(full), nickname, nickname


def person_name(rng: random.Random, registry: NameRegistry, country_code: str) -> tuple[str, str]:
    """Devuelve (nombre, apellidos). Dos apellidos en locales hispanos."""
    locale = COUNTRY_LOCALE.get(country_code, "es")
    given_pool, surname_pool = NAME_POOLS[locale]

    for _ in range(40):
        given = rng.choice(given_pool)
        if locale == "es" and rng.random() < 0.18:
            given = f"{given} {rng.choice(given_pool)}"
        first_surname = rng.choice(surname_pool)
        second_surname = rng.choice(surname_pool)
        while second_surname == first_surname:
            second_surname = rng.choice(surname_pool)
        surnames = f"{first_surname} {second_surname}"
        if registry.is_free(f"{given} {surnames}"):
            registry.claim(f"{given} {surnames}")
            return given, surnames

    given = rng.choice(given_pool)
    surnames = f"{rng.choice(surname_pool)} {rng.choice(surname_pool)}"
    registry.claim(f"{given} {surnames}")
    return given, surnames


def venue_name(rng: random.Random, registry: NameRegistry, place_name: str, nickname: str) -> str:
    patterns = [
        f"Parque {nickname}",
        f"Campo Municipal de {place_name}",
        f"Estadio {nickname} de {place_name}",
        f"Parque de Pelota {place_name}",
        f"Diamante {nickname}",
    ]
    return registry.claim(rng.choice(patterns))
