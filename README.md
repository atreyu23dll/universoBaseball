# Baseball Universe

Simulador de **ecosistemas de béisbol**: local, persistente, reproducible y
observable. El usuario define competiciones; el motor genera las instituciones,
las personas, las instalaciones, los calendarios y los partidos, y deja que el
mundo avance solo.

> **No** es un gestor de equipos. No contratas jugadores, no eliges tácticas ni
> administras un club. Eres el arquitecto de las competiciones y el observador
> del mundo.

## Estado real, sin adornos

| Etapa | Alcance | Estado |
|---|---|---|
| 0 | Monorepo, API, interfaz, base de datos, migraciones, pruebas, Docker | **Hecho** |
| 1 | Vertical: universo → liga independiente → generación → calendario → partidos → clasificación → postemporada → avance persistente | **Hecho** |
| 2 | Ascenso/descenso ejecutándose, grupos y divisiones | Tablas y validaciones; **el intercambio de clubes no está implementado** |
| 3 | Selecciones nacionales, elegibilidad por liga doméstica, franquicias internacionales | No empezado |
| 4 | Economía con libro mayor, patrocinios, fichajes, desarrollo de jugadores | No empezado |
| 5 | Lanzamiento por lanzamiento, física de la pelota, parque 2D | No empezado |
| 6 | Snapshots, exportación de universos, mapa histórico | No empezado |

La pantalla `/acerca` de la aplicación dice lo mismo, para que la interfaz no
insinúe más simulación de la que hay.

## Arranque rápido

### Con Docker (PostgreSQL, el modo de referencia)

```bash
cp .env.example .env          # opcional: los valores por omisión funcionan
docker compose up --build
```

- Interfaz: <http://127.0.0.1:5173>
- API y documentación: <http://127.0.0.1:8000/docs>
- Salud del servicio: <http://127.0.0.1:8000/health>

Las migraciones se aplican al arrancar el contenedor de la API. Los datos viven
en un volumen (`pgdata`), así que `docker compose down` y `up` conservan el
mundo. `make nuke` sí lo borra.

### Sin Docker (SQLite, arranque cero)

Para esto no hace falta ni base de datos ni contenedores:

```bash
make install        # crea .venv e instala las dependencias
make migrate        # crea data/baseball.db
make seed-demo      # universo de demostración con media temporada simulada
make run-api        # API en 127.0.0.1:8000
```

El frontend necesita Node:

```bash
cd frontend && npm install && npm run dev   # 127.0.0.1:5173
```

## El recorrido de la primera entrega

1. Crear un universo con su fecha inicial y su semilla.
2. Crear **una** competición: nombre, tipo, territorio, nivel, formato,
   clasificación, desempates y postemporada. Es lo único obligatorio.
3. Previsualizar: el motor muestra qué clubes, qué presupuestos, qué estadios y
   qué calendario saldrían, **y de dónde sale cada número**. Se puede volver a
   generar con otra semilla sin comprometer nada.
4. Confirmar. Se generan clubes, identidad visual, estadios con dimensiones,
   una población deportiva del territorio y el calendario.
5. Avanzar el reloj. Los partidos se simulan turno al bate por turno al bate, la
   clasificación se recalcula, la postemporada se construye con los clasificados
   reales y alguien se corona campeón.
6. Cerrar el navegador, reiniciar los contenedores: el mundo sigue donde estaba.

**No aparece ninguna liga inferior, porque nadie la creó.**

## Estructura

```
simulation/   motor puro: RNG, geografía, generación, calendario, partidos
backend/      FastAPI + SQLAlchemy + Alembic: API, servicios, persistencia
frontend/     SvelteKit + TypeScript: universos, asistente, fichas, reloj
data/         fixture geográfico local con su procedencia declarada
docs/         arquitectura, modelo de dominio, plan, fuentes, calibración, ADR
scripts/      calibración del motor y semilla de demostración
```

`simulation` no importa FastAPI, el ORM ni nada de `backend`, y hay una prueba
que falla si alguien lo rompe (`backend/tests/test_layering.py`).

## Comandos

```bash
make help              # lista todo
make test              # 109 pruebas, sin las de rendimiento (~1 min)
make test-all          # incluye las de rendimiento, que imprimen cifras
make test-postgres     # la batería del backend contra PostgreSQL en Docker
make lint              # ruff check + format --check
make calibrate         # mide el motor contra rangos de referencia conocidos
make verify            # lint + test + calibrate
```

## Lo que el proyecto promete y lo que no

**Sí:**

- **Reproducibilidad.** Misma versión, mismas reglas y misma semilla → mismo
  mundo. La aleatoriedad se deriva por contexto, así que añadir una opción a la
  interfaz no desplaza el futuro de todo lo demás.
- **Contabilidad que cierra.** El marcador es la suma de las carreras que
  anotaron corredores concretos, y cada box score pasa por un juego de
  invariantes antes de guardarse. Si algo no cuadra, el motor falla en vez de
  guardar una mentira plausible.
- **Procedencia.** Cada número generado guarda su procedimiento, su semilla y su
  derivación, consultables desde la ficha del club.
- **Honestidad sobre los datos.** Cada dato geográfico lleva su grado de
  confianza: `observed`, `estimated` o `fictional`. Las poblaciones son
  estimaciones de orden de magnitud, no censos; los índices son heurísticas
  nuestras; los clubes, las personas y los estadios son inventados.
- **Idempotencia y persistencia.** Repetir un avance con la misma clave no
  duplica nada; cada día se confirma en su propia transacción.

**No:**

- No es una predicción ni una simulación científica. Es **plausible**.
- No hay física de la pelota bateada, ni conteo de bolas y strikes.
- La economía no está calibrada contra nada: los presupuestos son heurísticas.
- No hay pronóstico meteorológico: hay un modelo estacional por latitud y
  altitud, declarado como modelo en la API y en la interfaz.
- Las distancias son en línea recta. No son tiempos de viaje.
- No se usan nombres, escudos ni patrocinadores reales.

Las desviaciones medidas del motor respecto al béisbol profesional están
enumeradas en [docs/simulation-calibration.md](docs/simulation-calibration.md),
incluidas las que no se han corregido.

## Documentación

- [Arquitectura](docs/architecture.md) — capas, persistencia, determinismo, qué no existe
- [Modelo de dominio](docs/domain-model.md) — entidades, separaciones, invariantes
- [Plan de implementación](docs/implementation-plan.md) — estado por etapas y siguiente iteración
- [Fuentes de datos](docs/data-sources.md) — qué es dato, qué es estimación, qué es ficción
- [Calibración](docs/simulation-calibration.md) — metodología, resultados y desviaciones
- ADR: [monolito modular](docs/adr/0001-modular-monolith.md) ·
  [persistencia dual](docs/adr/0002-persistencia-dual-y-gis-diferido.md) ·
  [RNG por contexto](docs/adr/0003-rng-derivado-por-contexto.md)

## Licencias y atribución

El fixture geográfico usa nomenclatura y centroides públicos; si se amplía con
datos de OpenStreetMap, aplican su
[licencia y atribución](https://www.openstreetmap.org/copyright) y su
[política de tiles](https://operations.osmfoundation.org/policies/tiles/).
Todo lo demás —clubes, personas, escudos, estadios, empresas— es ficticio y
generado por el motor.
