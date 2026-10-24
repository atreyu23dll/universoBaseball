# Arquitectura — Baseball Universe

> Estado: **Etapa 0, vertical de Etapa 1, movilidad de Etapa 2 y fases P0, P1,
> P2 y P3 del FIX V2 de Fase 1 implementadas**. De la Etapa 2 funciona el intercambio
> de clubes por ascenso y descenso con sus temporadas encadenadas; los grupos y
> divisiones dentro de una competición, no. Del FIX V2 funciona el formulario
> contraído a la competición, la economía de abajo arriba y el gazetteer
> mundial de GeoNames. Las etapas 3–6 están diseñadas pero **no**
> implementadas. Cada afirmación se marca como `[IMPLEMENTADO]`, `[PARCIAL]` o
> `[PLANIFICADO]`.

## 1. Forma general

Monolito modular con tres artefactos desplegables y un paquete de dominio puro:

```
frontend/   SvelteKit + TypeScript   (UI: universos, asistente de 9 pasos, tablas, reloj)
backend/    FastAPI + SQLAlchemy     (API REST, validación, orquestación, persistencia)
simulation/ Paquete Python puro      (motor: RNG, geografía, generación, economía, partidos)
data/       Fixtures y schemas       (geografía local con procedencia y ancla monetaria)
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

**Dos motores, dos niveles de rigor.** SQLite **no** comprueba la longitud
declarada de una columna de texto y PostgreSQL sí. Una grieta así ya rompió un
avance: un titular de evento de más de 240 caracteres pasaba en los tests y
fallaba en el motor de referencia, tumbando el día entero. Por eso
`record_event` recorta el titular al límite de su columna —el detalle completo
vive en `payload`, que es JSON y no tiene ese tope— y hay una prueba de
portabilidad que vigila que ningún camino nuevo escriba titulares de cualquier
longitud. La regla general: lo que la base de referencia rechaza no puede
depender de que la batería corra en SQLite, así que `make test-postgres` forma
parte de la verificación, no de los extras.

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

## 6. Frontera entre temporadas

[IMPLEMENTADO] Al cerrar una edición, el avance del día cruza la frontera de
temporada dentro de **la misma transacción** que la provocó
(`app/application/season_service.py`):

1. Si la competición no está vinculada a ninguna otra, abre su temporada
   siguiente con los clubes que ya pertenecen a ella.
2. Si está vinculada, **espera** a que todas las ligas de la escalera cierren la
   misma temporada. Entonces resuelve el intercambio y solo después abre las
   ediciones nuevas: la liga de arriba no puede tener calendario antes de saber
   quién sube.

El plan de ascensos y descensos lo resuelve el motor puro
(`simulation/competitions/mobility.py`), que recibe clasificaciones ya resueltas
y devuelve movimientos con su motivo. El servicio lo aplica:

- cierra las `club_memberships` vigentes y abre las nuevas, **sin tocar
  `club.id`**, su estadio, su plantilla, su caja, su deuda ni su historia;
- reescala el presupuesto hacia el nivel de la nueva categoría una fracción
  configurable (heurística, con su procedencia anotada) y mueve la reputación
  despacio;
- registra un `SimulationEvent` por movimiento y una fila en
  `season_transitions` cuya clave única `(competición superior, temporada)` hace
  **idempotente** la operación: reintentar el avance no mueve a nadie dos veces.

La pertenencia tiene vigencia por temporadas (`start_season`, `end_season`)
además de por edición, porque un ascenso se resuelve cuando la edición de
destino todavía no existe.

Consecuencia en el contrato del reloj: `until_season_end` ya no puede significar
«hasta que no queden partidos pendientes» —eso no vuelve a ocurrir nunca—, así
que el avance apunta las ediciones abiertas al empezar y para cuando todas han
terminado.

Antes de mover a nadie, el servicio **liquida la temporada de cada club**
(`app/application/club_evolution_service.py`). El orden no es casual: un club
que cierra no asciende, y una plaza no puede adjudicarse a quien ya no existe.

1. `simulation/economy/season_close.py` calcula **lo cobrado y lo pagado**, que
   no es lo previsto: hay socios que dejan de pagar, patrocinadores que
   incumplen y partidos que no se jugaron y no vendieron entradas. Las
   obligaciones, en cambio, se pagan enteras —con caja o con deuda— y lo que no
   se cubre se convierte en deuda con interés.
2. `simulation/economy/evolution.py` decide **en qué se convierte** el club: su
   afición se mueve por lo que hizo en el campo, su alcance en la zona sube o
   baja con las cuentas, su sede mejora o se degrada, y su forma de gobierno se
   formaliza con años, arraigo y solvencia.
3. Dos temporadas consecutivas sin poder cubrir sus obligaciones y el club deja
   de competir. Conserva su fila, su historia y sus títulos; lo que no ocurre es
   que se le regale el dinero que le falta para mantener el número de equipos de
   la liga.

Después, una segunda pasada **vuelve a presupuestar** la temporada siguiente de
los supervivientes (`simulation/generation/season_forecast.py`) con la misma
función que usó la generación, con la afición y el alcance ya evolucionados y
con los recursos de la zona repartidos entre los clubes que quedan. La bolsa
publicitaria local se recalcula desde el territorio, así que no crece porque un
club crezca: lo que uno gana lo pierden sus vecinos.

Queda todo escrito en `club_season_ledgers` —clave única `(club_id, season)`,
que vuelve **idempotente** la liquidación igual que `season_transitions` lo hace
con el intercambio— y en `club_organization_changes`, con la causa de cada
cambio. La ficha del club lo muestra: lo real frente a lo previsto, asiento por
asiento.

## 6 bis. Divisiones dentro de una competición

[IMPLEMENTADO] El bloque `structure` del reglamento convierte una competición
de tabla única en una de divisiones, grupos o conferencias. Lo que cambia:

- **El reparto** (`simulation/competitions/groups.py`): por cercanía —los
  vecinos juntos, que es lo que abarata los viajes— o repartiendo los clubes con
  más recursos en serpiente. El usuario puede además declarar los nombres y las
  plazas de cada grupo. Cada club queda con el motivo de su división escrito en
  la procedencia.
- **El calendario** (`simulation/competitions/schedule.py`): `intra_cycles`
  vueltas contra los de su grupo e `inter_cycles` contra los demás. Esa
  asimetría es el sentido de una división, y tiene dos consecuencias que se
  declaran: los partidos por club dejan de ser el objetivo pedido y pasan a ser
  una consecuencia de las vueltas, y con grupos de tamaños distintos no todos
  juegan lo mismo. Las localías se reparten con una **orientación euleriana**
  del grafo de enfrentamientos, que es lo que evita que una vuelta impar deje a
  unos clubes jugando casi todo en casa. Si las vueltas dentro y fuera
  coinciden, el calendario es el round-robin de siempre.
- **La clasificación** (`simulation/competitions/standings.py`): sigue habiendo
  una fila por club con **todos** sus partidos; el grupo solo añade el puesto
  dentro de él. Una tabla de división no es un torneo aparte.
- **La postemporada** (`simulation/competitions/playoffs.py`): clasifican los
  primeros de cada grupo más los repechajes de la tabla general, y queda
  registrado quién entró por qué ruta. Con divisiones, las plazas de playoff las
  fija la estructura: el reglamento rechaza un `playoffs.slots` que no cuadre,
  para que no existan dos números que puedan contradecirse.

El grupo se guarda en `edition_entries.group_key`, por edición y no por club,
porque el reparto se rehace cada temporada: un club que asciende entra en la
división que le toca por geografía sin dejar de ser el mismo club.

La postemporada admite **plazas que no son potencia de dos**: con seis
clasificados el cuadro es de ocho y las dos mejores siembras esperan en la
segunda ronda. `PlayoffRules` deriva el tamaño del cuadro, los pases directos y
las rondas necesarias, de modo que el reglamento rechaza unas longitudes de
serie que no cuadren con el cuadro real. Los pases directos se guardan en
`competition_editions.playoff_byes` porque la ronda siguiente se construye otro
día, en otra transacción.

## 6 ter. El asistente ve lo que pide

[IMPLEMENTADO] `POST /schedule/preview`
(`app/application/schedule_preview_service.py`) responde a «¿y si pongo esto?»
con el calendario, los cruces y el cuadro que producirían unos parámetros. No
necesita universo ni competición y **no escribe nada**: llama a `build_schedule`,
`group_sizes` y `seed_bracket`, los mismos que construyen la competición de
verdad, así que lo que la interfaz dibuja no es una maqueta.

Existe porque el paso del calendario pide seis números que se multiplican entre
sí —partidos objetivo, partidos por serie, días entre series, descanso semanal,
vueltas dentro y fuera de la división— y leerlos no dice nada. La vista pinta el
resumen, el reparto de cada club entre partidos de su división y de fuera, la
matriz de cruces, las dos primeras semanas día a día y el cuadro con la ruta de
cada clasificado. Todo son tablas y listas reales, navegables con teclado, y
cada color lleva su número al lado: el color guía, no informa por su cuenta.

[PLANIFICADO] Extracción de cupos hacia copas (`QualificationPath`
ejecutándose); fusiones y refundaciones de clubes, que V2 §6.3 menciona y aquí
no existen.

## 7. Geografía: gazetteer mundial y qué se sabe de cada sitio

[IMPLEMENTADO] Dos fuentes con papeles distintos:

- **`gazetteer_*`** (global, compartido entre universos): GeoNames importado.
  252 países con su moneda ISO 4217, 3 865 divisiones de primer nivel y 236 632
  localidades con variantes de nombre. Identificador propio más referencia
  externa estable `(source, source_id)`.
- **`places` / `region_profiles`** (por universo): la copia local del territorio
  que esa partida usa, materializada desde el gazetteer al crear una
  competición, para que cada universo pueda calibrar sus índices sin tocar los
  demás.

La resolución recorre `unresolved → candidates → user_selected → verified |
incomplete`. Lo que la competición guarda es el **identificador** de la entidad,
no el texto que escribió el usuario; un nombre a mano devuelve
`GEOGRAPHY_UNRESOLVED`.

Cobertura y conocimiento son cosas distintas, y el modelo las distingue:
GeoNames da identidad, jerarquía, coordenadas, altitud, población y moneda
—todo `observed`, con fuente citable—, y **no** da economía local, cultura
beisbolística ni infraestructura deportiva. Esos índices salen como
`scenario_assumption` con valor neutral, nunca deducidos del país, y si el
universo ya tiene ese lugar calibrado a mano se reutilizan sus índices.

Sin ancla monetaria curada, las cuentas de los clubes de esa jurisdicción salen
con `insufficient_data` y los conceptos declarados sin cifra. Ver
`docs/adr/0006-gazetteer-mundial-geonames.md`.

## 8. Causalidad de la generación

[IMPLEMENTADO] El orden no es un detalle de implementación: es el contrato que
impide que una etiqueta del formulario decida el dinero (FIX V2 §7.2, ADR 0005).

```text
territorio + reglas de la competición
  → recursos locales finitos (patrocinio, socios, campos) — y disputados
    → organización propia de cada club (gobierno, sede, ambición)
      → instalación compatible con su acuerdo de sede
        → cuentas de abajo arriba: lo que recauda y lo que puede pagar
          → nivel efectivo de la competición, que emerge de todo lo anterior
            → talento que esa competición atrae del mercado compartido
```

Lo hace cumplir el código, no la buena voluntad: `generate_clubs` ya no recibe
la población deportiva, y `CompetitionContext.level` **lanza una excepción** si
alguien lo consulta antes de que `resolve_effective_level` lo haya calculado.

El único punto donde un índice relativo se convierte en dinero es el **ancla
monetaria** del territorio (`EconomicAnchor`: moneda de curso legal y gasto
mensual de referencia de un hogar, estimado y fechado). Sin ancla no hay
importes: las cuentas salen con `insufficient_data` y la interfaz lo dice.

La frontera de responsabilidades está en el DTO, no solo en la interfaz: el
reglamento admite `participation_modality`, `eligibility`, `admission` y
`financial_regulations`, y **rechaza** con el código
`DEPRECATED_CLUB_GENERATION_FIELD` cualquier campo que intente decidir el
presupuesto, la propiedad, el personal o la instalación de los clubes.

## 9. Motor de partidos

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

## 10. Qué no existe todavía

Dicho sin rodeos, para que nadie lo busque en el código:

- **Mapa cartográfico.** La geografía se resuelve y se consulta como texto, que
  es lo accesible y lo que pide el requisito; no hay vista MapLibre ni polígonos
  descargados de geoBoundaries.
- **Coste de referencia para 246 países.** Se conoce la moneda de 251 de 252,
  pero el ancla que convierte índices en importes solo está curada para cinco:
  los demás territorios generan mundos completos sin cifras económicas.
- Grupos, divisiones y conferencias dentro de una misma competición: hoy toda
  competición es una tabla única (resto de la Etapa 2).
- `QualificationPath` **ejecutándose**: las rutas de cupos se registran y se
  validan, pero no extraen participantes (Etapa 3).
- Consecuencias del ascenso más allá del presupuesto y la reputación: no hay
  renegociación de contratos ni ajuste de plantilla al cambiar de categoría
  (Etapa 4).
- Selecciones nacionales, elegibilidad por liga doméstica, preeliminatorias (Etapa 3).
- Economía con libro mayor, patrocinios, fichajes, IA institucional (Etapa 4).
- Lanzamiento por lanzamiento, clima por fecha real, vista 2D del parque (Etapa 5).
- Snapshots, exportación de universos, mapa histórico (Etapa 6).
- Mapa MapLibre: la UI de Etapa 1 usa listas y tablas.
