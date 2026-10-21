# ADR 0001 — Monolito modular, no microservicios

**Fecha:** 2026-10-20 · **Estado:** aceptado

## Contexto

La aplicación es local, personal y de un solo usuario, pero el dominio es
grande: generación procedural, calendarios, partidos, economía, geografía.
Existe la tentación de separar cada subdominio en un servicio.

## Decisión

Un monolito modular con un paquete de dominio puro (`simulation`) que no importa
el framework web ni el ORM, y un backend (`backend`) que lo orquesta.

## Razones

- La simulación es un proceso intensivo en CPU con estado fuertemente acoplado
  (un partido necesita plantillas, estadio, clima y reglas a la vez). Partirlo en
  servicios añadiría serialización y latencia sin ganar nada en una máquina.
- El límite que **sí** importa es «dominio puro ↔ infraestructura», y ese se
  obtiene con paquetes y una prueba de capas, no con procesos.
- Mover el avance de tiempo a un proceso aparte más adelante es cambiar quién
  llama a `sim_service.advance()`. No exige romper el dominio.

## Consecuencias

- `backend/tests/test_layering.py` falla si `simulation` importa FastAPI,
  SQLAlchemy o `app.*`.
- Un worker separado y una cola en Postgres son un añadido posterior de
  infraestructura, no una reescritura.
- No hay descubrimiento de servicios, ni gateway, ni tracing distribuido que
  mantener.
