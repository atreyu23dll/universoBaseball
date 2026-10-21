# Datos locales

## `fixtures/places.json`

Fixture geográfico del que arrancan todos los universos. Se copia dentro de cada
universo al crearlo, así que calibrar un índice en una partida no afecta a las
demás.

**Cada campo lleva su grado de confianza.** Ver
[`docs/data-sources.md`](../docs/data-sources.md) para el detalle de qué es dato
público, qué es estimación nuestra y qué está inventado. Resumen:

- Nombres, códigos ISO, husos horarios y centroides: públicos (`observed`).
- Poblaciones: **estimaciones de orden de magnitud** con año de referencia
  declarado. Sirven para escalar mercados en la simulación; **no son un censo y
  no deben citarse como tal**.
- Índices de economía, cultura beisbolística, coste de vida e infraestructura:
  heurísticas propias en escala relativa 0–1, calibrables por el usuario.
- Subzonas de ciudad: áreas sintéticas inventadas (`fictional`). No corresponden
  a colonias reales.

## `*.db`

Bases SQLite locales del modo de arranque cero. **No se versionan**
(`.gitignore`). `make reset-db` las borra.

## `schemas/`

Reservado para esquemas JSON exportables del `RuleSet`. Hoy el contrato vive
tipado en `simulation/competitions/ruleset.py`, que es la única fuente de
verdad; duplicarlo aquí a mano sería una copia que se desincroniza.
