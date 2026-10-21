# Arquitectura — Baseball Universe

> Estado: **Etapa 0 + vertical de Etapa 1 implementadas**. Las etapas 2–6 están
> diseñadas (contratos y tablas previstas) pero **no** implementadas. Cada
> afirmación de este documento se marca como `[IMPLEMENTADO]`, `[PARCIAL]` o
> `[PLANIFICADO]`.

## 1. Forma general

Monolito modular con tres artefactos desplegables y un paquete de dominio puro:

```
frontend/   SvelteKit + TypeScript   (UI: universos, wizard de liga, tablas, reloj)
backend/    FastAPI + SQLAlchemy     (API REST, validación, orquestación, persistencia)
simulation/ Paquete Python puro      (motor: RNG, generación, calendario, partidos)
data/       Fixtures y schemas       (geografía local marcada por procedencia)
```

Regla de dependencias (verificada por `backend/tests/test_layering.py` [IMPLEMENTADO]):

```
frontend  →  backend  →  simulation  →  (stdlib + pydantic)
```

`simulation` **no** importa FastAPI, SQLAlchemy ni nada de `backend`. El motor se
puede ejecutar desde un script o un test sin levantar servidor ni base de datos;
`simulation/tests` corre sin Postgres. La inversa está prohibida: `backend`
convierte entre filas ORM y dataclasses del dominio en
`backend/app/application/`.

## 2. Capas

```
[SvelteKit]  rutas /universes, /universes/[id], wizard, inspector, reloj
      ↕ REST  (/api/v1, JSON)
[FastAPI]    app/api/v1/*  — validación Pydantic, códigos de error, paginación
      ↕
[Application Services]  app/application/*  — casos de uso, transacciones,
                        idempotencia, conversión dominio ↔ persistencia
      ↕
[Simulation Domain]     simulation/*  — puro, determinista, sin I/O
      ↕
[Repositories/UoW]      app/infrastructure/*  — SQLAlchemy, sesión por unidad
      ↕
[PostgreSQL | SQLite]   migraciones Alembic compartidas
```

### Qué vive en cada capa

| Capa | Responsabilidad | Prohibido |
|---|---|---|
| `api` | HTTP, validación de entrada, serialización | lógica de negocio, SQL |
| `application` | casos de uso, transacción, idempotencia | reglas de béisbol |
| `simulation` | reglas, generación, partidos, calendario | I/O, ORM, red, reloj real |
| `infrastructure` | ORM, sesiones, migraciones, adaptadores | decisiones deportivas |

## 3. Persistencia: Postgres y SQLite

[IMPLEMENTADO] Una sola definición de modelos y **una sola** cadena de
migraciones sirve a dos motores:

- **PostgreSQL 16** — modo de referencia, usado por `docker compose`.
- **SQLite** — modo de arranque cero, usado por los tests y por `make run-local`.

Los tipos se eligieron portables a propósito: `JSONType` es `JSON` con variante
`JSONB` en Postgres, el dinero es `Numeric(16,2)` y las coordenadas son dos
columnas `Float` (`lat`, `lon`) más una columna opcional de geometría.
Ver `docs/adr/0002-persistencia-dual-y-gis-diferido.md`.

[PLANIFICADO] PostGIS: la geometría se consulta hoy con distancia haversine
calculada en Python (`simulation/geography/distance.py`). El día que haga falta
una consulta espacial real (polígonos, contención, vecindad) se añade la columna
`geom` y un índice GiST en una migración condicionada al dialecto.

## 4. Determinismo

[IMPLEMENTADO] El universo guarda un `master_seed`. Toda aleatoriedad se obtiene
de `simulation.core.rng.rng_for(master_seed, *path)`, que deriva una semilla con
BLAKE2b sobre la ruta de contexto (`("universe", "clubs", edition_id, slot)`).
Consecuencia buscada: **cada contexto tiene su propio flujo**, así que añadir una
opción nueva a la interfaz —o simular un partido más— no desplaza el futuro de
todo lo demás por consumir números de un RNG compartido.

Lo que se persiste para reproducir: `master_seed`, `sim_version`,
`ruleset_version` por edición, y `seed` por partido. `generation_provenance`
guarda, por entidad generada, el procedimiento, la semilla y los supuestos.

## 5. Avance del tiempo

[IMPLEMENTADO] `POST /api/v1/universes/{id}/sim/advance` crea un `sim_job`,
devuelve `job_id` y procesa en una `BackgroundTask` de FastAPI; el cliente
consulta `GET .../sim/status`. El avance es idempotente por
`Idempotency-Key`: la misma clave devuelve el job original sin volver a simular.

Un **lock por universo** (fila `universes.sim_lock_token` con comparación y
canje atómico) impide dos avances simultáneos sobre el mismo universo.

[PARCIAL] El "worker" es hoy una tarea en proceso dentro del backend, no un
proceso separado. La frontera ya está donde debe: `application/sim_service.py`
no sabe quién lo llama. Mover a un proceso aparte con cola en Postgres es un
cambio de `runner`, no de dominio.

### Cómo llega la interfaz a la API

[IMPLEMENTADO] El navegador solo habla con el origen del frontend. El servidor
de SvelteKit reenvía `/api/*` al backend, con el destino en `BU_API_URL`
(`http://api:8000` en Docker, `http://127.0.0.1:8000` por omisión).

Esto empezó siendo un proxy de Vite, que **solo existe en `vite dev`**: en el
contenedor se sirve la compilación de producción con el adaptador de Node y cada
llamada de la interfaz recibía un 404 con el HTML de la página. El proxy vive
ahora en una ruta de servidor de SvelteKit, de modo que desarrollo y producción
recorren el mismo camino, y `scripts/smoke_stack.sh` comprueba el stack por ese
camino y no por atajos.

[PLANIFICADO] WebSocket `/sim/stream`. Hoy la UI hace polling del endpoint de
estado. El contrato de mensajes está redactado en `docs/implementation-plan.md`
pero no hay servidor WS: no lo anunciamos como disponible.

## 6. Motor de partidos

[IMPLEMENTADO] Nivel 1 de los tres que pide la especificación: máquina de
estados **turno de bateo por turno de bateo**. No existe una fórmula que elija
ganador y después invente estadísticas: el marcador es la suma de carreras
producidas por eventos individuales, y el box score se valida contra invariantes
después de cada partido (`simulation/core/invariants.py`).

Cada turno resuelve: matchup bateador/lanzador (log5 sobre tasas base de la
liga), efecto de parque (dimensiones, altitud, viento), fatiga del abridor,
decisión de relevo, resultado (BB/HBP/SO/HR/3B/2B/1B/out en juego con error y
doble matanza), avance de corredores y anotación.

[PLANIFICADO] Niveles 2 (lanzamiento por lanzamiento) y 3 (trayectoria física).
El motor expone la interfaz `MatchEngine` para que convivan calibrados entre sí.

## 7. Qué no existe todavía

Dicho sin rodeos, para que nadie lo busque en el código:

- Ascenso/descenso transaccional y grafo de relaciones **ejecutándose**: las
  tablas y las validaciones de ciclo existen; el intercambio de clubes al cerrar
  temporada no (Etapa 2).
- Selecciones nacionales, elegibilidad por liga doméstica, preeliminatorias (Etapa 3).
- Economía con libro mayor, patrocinios, fichajes, IA institucional (Etapa 4).
- Lanzamiento por lanzamiento, clima por fecha real, vista 2D del parque (Etapa 5).
- Snapshots, exportación de universos, mapa histórico (Etapa 6).
- Mapa MapLibre: la UI de Etapa 1 usa listas y tablas.
