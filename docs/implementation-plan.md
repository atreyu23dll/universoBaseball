# Plan de implementación — Baseball Universe

## Estado por etapas

| Etapa | Alcance | Estado |
|---|---|---|
| 0 | Monorepo, FastAPI, SvelteKit, Postgres/SQLite, Alembic, tests, Docker | **Hecho** |
| 1 | Vertical: universo → liga independiente → generación → calendario → partidos → tabla → avanzar → persistir | **Hecho** |
| 2 | Motor declarativo de relaciones, ascenso/descenso transaccional, grupos/divisiones | Tablas y validaciones; sin intercambio |
| 3 | Internacional: franquicias por ciudad, selecciones, elegibilidad por liga doméstica | No empezado |
| 4 | Personas e IA: desarrollo por edad, scouts falibles, ledger, patrocinios, fichajes | No empezado |
| 5 | Béisbol detallado lanzamiento por lanzamiento, clima, parque 2D, replay | No empezado |
| 6 | Escala, snapshots, historia, exportación | No empezado |

## Etapa 0 — hecho cuando

- [x] `simulation` importable y testeable sin servidor ni base de datos.
- [x] FastAPI con `/health` y configuración por entorno.
- [x] SvelteKit tipado que consume la API real.
- [x] Alembic con migración inicial que corre en SQLite y en PostgreSQL.
- [x] `docker compose` con volumen persistente para Postgres.
- [x] `make test`, `make lint` verdes.

## Etapa 1 — hecho cuando

> Un usuario crea «Liga Municipal de Ciudad Juárez» de 12 clubes y simula una
> temporada completa sin editar un solo club.

- [x] Crear/cargar universo con semilla y fecha inicial.
- [x] Crear liga **independiente** municipal o nacional desde el wizard.
- [x] Perfiles geográficos desde fixture local con procedencia marcada.
- [x] Generación seeded de clubes, marca, estadios, plantillas y personas.
- [x] Calendario válido con balance de localías y días de descanso.
- [x] Motor de partidos por turno de bateo con box score consistente.
- [x] Clasificación, calendario, plantillas y fichas vía API y UI.
- [x] `advance` idempotente, persistente y con lock por universo.
- [x] Playoffs al cierre de la temporada regular.

## Etapa 2 — contrato previsto (no implementado)

La relación es la autoridad única. Al cerrar dos ediciones vinculadas:

1. Resolver clubes que suben desde la inferior con `lower_selection`.
2. Resolver clubes que bajan desde la superior con `upper_selection`.
3. Verificar elegibilidad/licencias; aplicar política si falla.
4. Aplicar en **una** transacción: cerrar `club_memberships` viejas, abrir nuevas,
   preservando `club.id`, estadio, deudas, plantilla e historia.
5. Registrar `SimulationEvent` por cada movimiento.

Con varias ligas alimentadoras la cuota **total** vive en la relación de la
competición superior; nunca `2 ↔ 2` por rama.

## Contrato de WebSocket previsto (no implementado)

Mensajes versionados: `tick_started`, `tick_completed`, `game_completed`,
`league_updated`, `job_progress`, `job_failed`, cada uno con `v`, `job_id` y
`universe_id`. Perder la conexión no cancela nada: el cliente recupera estado
por `GET /sim/status`. Hoy la UI hace polling de ese endpoint.

## Orden recomendado para la siguiente iteración

1. Grupos/divisiones y desempates completos en `competitions/standings.py`.
2. Intercambio ascenso/descenso transaccional + casos C04, C05, C06, C07.
3. Mover el avance a un proceso worker con cola en Postgres y añadir WebSocket.
4. `QualificationPath` ejecutándose (caso C08, C12) y liga internacional de
   clubes con franquicias por ciudad (C11).
