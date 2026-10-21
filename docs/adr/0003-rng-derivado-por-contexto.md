# ADR 0003 — RNG derivado por contexto, no un flujo global

**Fecha:** 2026-10-20 · **Estado:** aceptado

## Contexto

El universo debe ser reproducible: misma versión + mismas reglas + misma semilla
→ mismo mundo. La forma ingenua es un único `random.Random(master_seed)`
compartido por todo el motor.

## Problema con el flujo único

El orden de consumo se vuelve parte del contrato. Añadir una casilla a la
interfaz que genere un club con un atributo más desplaza todos los números
posteriores, y una temporada entera cambia de resultado por una razón que no
tiene que ver con las reglas. La especificación lo señala explícitamente.

## Decisión

Toda aleatoriedad pasa por:

```python
rng_for(master_seed, "clubs", edition_id, slot_index)
```

que deriva la semilla con BLAKE2b sobre la ruta de contexto serializada y
devuelve un `random.Random` nuevo. Cada contexto tiene su propio flujo
independiente.

## Consecuencias

- Generar un club más no altera los jugadores de los clubes ya generados.
- Simular el partido 500 de la temporada da el mismo resultado se simule antes o
  después que el 499, porque su semilla sale de `("game", game_key)`.
- El coste es crear un objeto `Random` por contexto. Medido en
  `simulation/tests/test_rng.py`: irrelevante frente a la simulación del partido.
- La ruta de contexto es parte del contrato de reproducibilidad: renombrar un
  tramo cambia el mundo. Por eso `PROCEDURE_VERSION` se guarda en
  `generation_provenance`.
