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
| 2 | Ascenso/descenso ejecutándose, grupos y divisiones | **Movilidad hecha** (intercambio, cuota única, requisitos, temporadas encadenadas); **sin grupos ni divisiones** |
| 3 | Selecciones nacionales, elegibilidad por liga doméstica, franquicias internacionales | No empezado |
| 4 | Economía con libro mayor, patrocinios, fichajes, desarrollo de jugadores | **Libro mayor de temporada hecho** (liquidación, deuda, desaparición de clubes); sin patrocinios como entidad, fichajes ni desarrollo |
| 5 | Lanzamiento por lanzamiento, física de la pelota, parque 2D | No empezado |
| 6 | Snapshots, exportación de universos, mapa histórico | No empezado |

Además, el **FIX V2 de Fase 1** —un documento posterior que corrige el
formulario de creación, la economía y la generación de clubes, y que prevalece
sobre la especificación maestra en esos tres puntos— va por aquí:

| Fase del fix | Alcance | Estado |
|---|---|---|
| P0 | Pruebas que reproducen los defectos observados | **Hecho** |
| P1 | Formulario contraído a la competición: modalidad única y elegibilidad | **Hecho** |
| P3 | Economía de abajo arriba e instituciones autónomas y heterogéneas | **Hecho** |
| P2 | Geocodificación mundial (GeoNames + PostGIS + geoBoundaries) | **Hecho** |
| P4 | Preview con huella de intención y confirmación idempotente | **Hecho** |
| P5 | Evolución institucional en el tiempo: liquidación, cambio y desaparición | **Hecho** |

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

El navegador habla **siempre con el mismo origen**: el servidor de SvelteKit
reenvía `/api/*` al backend (`src/routes/api/[...path]/+server.ts`, destino en
`BU_API_URL`). El mismo camino en desarrollo y en producción, y sin depender de
CORS. Para comprobar el stack tal como lo ve el navegador:

```bash
docker compose up -d --wait
make smoke-stack
```

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
   clasificación, desempates y postemporada. Es lo único obligatorio. Si ya
   existe otra competición, el mismo asistente permite vincularla por ascenso y
   descenso —o como filial o juvenil— sin salir del formulario.
3. Previsualizar: el motor muestra qué clubes saldrían, **cómo se organiza cada
   uno** —quién lo gobierna, si tiene propietario, en qué campo juega—, de dónde
   sacaría cada peso y qué calendario tendría. Se puede regenerar con otra
   semilla sin comprometer nada, pero no editar club por club: esas decisiones
   son de cada institución.
4. Confirmar. Se generan clubes, identidad visual, estadios con dimensiones,
   una población deportiva del territorio y el calendario.
5. Avanzar el reloj. Los partidos se simulan turno al bate por turno al bate, la
   clasificación se recalcula, la postemporada se construye con los clasificados
   reales y alguien se corona campeón.
6. Cerrar el navegador, reiniciar los contenedores: el mundo sigue donde estaba.

**No aparece ninguna liga inferior, porque nadie la creó.**

## Ascenso y descenso, si los pides

Se vinculan en el paso B del asistente al crear la segunda liga, o después
entre dos que ya existen, desde el grafo de competiciones. A partir de ahí:

- Las plazas se definen **una vez**, en la relación. Las dos ligas muestran el
  mismo número, y editarlo desde cualquiera de las dos lo cambia en las dos.
- Con varias ligas alimentadoras la cuota es un **total** que se reparte entre
  ellas. Cuatro ligas con cuota 3 mueven tres clubes, no doce.
- El intercambio espera a que **todas** las ligas vinculadas cierren su
  temporada, se aplica en una transacción y queda en un libro que impide
  aplicarlo dos veces.
- Los clubes que suben y bajan son los mismos clubes: conservan identificador,
  estadio, plantilla, caja, deuda, títulos e historia. Lo que cambia es su
  inscripción, y su presupuesto se acerca una fracción al de su nueva categoría.
- Se pueden exigir requisitos de ascenso (aforo, deuda sobre presupuesto). Si un
  club no los cumple, sube el siguiente clasificado, o la plaza se bloquea —y
  entonces tampoco desciende nadie por ella—, o asciende por excepción. Las tres
  políticas quedan registradas con su motivo.
- Al cerrar la temporada, el mundo abre la siguiente con los clubes que ya
  existen: no se regenera nada.
- Antes de mover a nadie, cada club **liquida** su temporada. Un club que
  desaparece por insolvencia no asciende ni desciende: su plaza queda vacante.

Una **filial** o una **liga juvenil** son otra cosa: mueven jugadores y nunca
clubes. Y mandar el campeón a una copa no le cuesta la independencia a nadie.

## Lo que pasa cuando acaba el año

La temporada no se repite: se liquida. Cada club cuenta lo que **cobró**, que no
es lo que había previsto —hay socios que dejan de pagar, patrocinadores que
incumplen y partidos que no se jugaron y no vendieron entradas—, mientras que
sus obligaciones se pagan enteras, con caja o con deuda.

Con ese resultado, la institución cambia: la afición crece si el equipo ganó y
se encoge si perdió, el alcance en su zona sube con las cuentas sanas y baja con
las cuentas en rojo, la sede mejora cuando hay caja y ambición para pagarla y se
degrada cuando no hay para mantenerla, y un colectivo con años de historia,
arraigo y solvencia acaba constituyéndose en asamblea de socios. Nunca al revés
por capricho, y nunca de golpe.

Y dos temporadas consecutivas sin poder cubrir sus obligaciones y el club deja
de competir. **No se le regala el dinero que le falta** para mantener el número
de equipos de la liga: la competición se queda con los clubes que su territorio
puede sostener. El club conserva su ficha, su historia y sus títulos; deja de
jugar, y queda dicho con su causa y su cifra.

Y el año siguiente se presupuesta de nuevo con ese mundo: más afición significa
más cuotas y más taquilla, pero la bolsa de patrocinio de la zona es la misma de
siempre, así que lo que un club gana lo pierden sus vecinos y lo que deja uno
que desaparece se reparte entre los que siguen.

Todo esto está en la ficha del club: el libro mayor de cada temporada, asiento
por asiento, con lo previsto al lado de lo real, y su historia institucional con
el motivo de cada cambio.

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
make test              # 193 pruebas, sin las de rendimiento (~6 min)
make smoke-stack       # comprueba el stack por el camino del navegador
make test-all          # incluye las de rendimiento, que imprimen cifras
make test-postgres     # la batería del backend contra PostgreSQL en Docker
make lint              # ruff check + format --check
make calibrate         # mide el motor contra rangos de referencia conocidos
make import-geonames   # descarga e importa el gazetteer mundial
make verify            # lint + test + calibrate
```

## Cualquier lugar del mundo

El territorio de una competición se resuelve contra un gazetteer mundial
importado de **GeoNames**: 252 países con su moneda de curso legal, 3 865
divisiones administrativas de primer nivel y **236 632 localidades** de 500
habitantes o más, con sus variantes de nombre.

```bash
make import-geonames          # descarga (~17 MB) e importa el mundo
make import-geonames-sample   # solo el extracto versionado, sin red
```

Buscas, el sistema te ofrece **candidatos desambiguados** por país, jerarquía y
tipo de entidad, y eliges uno. Lo que se guarda es el identificador de esa
entidad, no el texto que escribiste: un nombre a mano devuelve
`GEOGRAPHY_UNRESOLVED` y te manda a buscar. Una búsqueda sin resultados dice que
no hay; nunca se sustituye por tres ciudades predefinidas.

**Lo que se sabe y lo que no, por separado.** De Kampala el simulador sabe su
jerarquía (Uganda · Central Region · Kampala District), su población
—1 680 600, con el `geonameid` que lo respalda— y su moneda, UGX. No sabe su
economía local, su cultura beisbolística ni su infraestructura deportiva: esos
índices quedan como **supuesto declarado** con valor neutral, y no se deducen
del país, porque eso sería un estereotipo disfrazado de dato.

Tampoco hay coste de referencia curado para Uganda, así que una liga llanera en
Kampala **se genera entera** —clubes con formas de gobierno distintas, sedes,
plantillas, calendario, partidos, clasificación— y sus cuentas salen con los
conceptos declarados y **sin importes**, marcadas como datos insuficientes. Antes
un hueco declarado que una cifra inventada.

Si un territorio no tiene polígono administrativo publicado, se dice y se ofrece
delimitar por **radio** desde su centroide, advirtiendo de que es una
aproximación en línea recta que no respeta fronteras.

## Quién decide qué

Esta frontera es el contrato del producto, y está en el código, no solo en la
documentación:

| Lo define **el usuario** | Lo genera y administra **el motor** |
|---|---|
| Nombre, clase y territorio de la competición | Qué clubes existen, cómo se llaman y qué historia tienen |
| **Modalidad de participación** (llanera, amateur organizada, escolar, semiprofesional, profesional) | Forma de gobierno de cada club, con o sin propietario |
| Edad, corte y salvaguardas | Cómo accede cada club a un terreno de juego |
| Requisitos de admisión verificables: licencia, seguridad, aforo mínimo | Cuánto dinero reúne y en qué se lo gasta |
| Normas económicas de la liga: prohibir salarios, tope, inscripción | Quién cobra y quién es voluntario en cada club |
| Calendario, reglas de juego, clasificación y postemporada | Qué instalación tiene y de qué tamaño |
| Vínculos con otras competiciones | Qué jugadores atrae del mercado compartido |

El asistente **no pregunta** por presupuestos, financiación, propiedad de
estadios, estructura administrativa ni nivel de riqueza, y la API **rechaza**
esos campos con un código propio si alguien los envía a mano. Un club llanero
puede tener patrocinio y un club profesional puede ser modesto: lo que decide es
su entorno, no una etiqueta.

## De dónde sale el dinero

Cada club estima primero lo que puede recaudar en su zona —cuotas, su parte del
patrocinio local, taquilla si controla el recinto, apoyos según su gobierno,
derechos de emisión solo si tiene audiencia que los justifique— y después decide
en qué gastarlo: primero lo obligatorio (campo, arbitraje, viajes sobre
distancias reales, material, uniformes, seguro si hay menores), y solo con el
margen lo demás. **El presupuesto es el resultado, no el punto de partida.**

Los recursos de una zona son finitos: la bolsa publicitaria de un barrio se
reparte entre los clubes que la disputan, y si hay menos campos que clubes se
comparte sede. Plantar veinte equipos en el mismo barrio no multiplica el
dinero: lo divide.

Todo importe es un múltiplo del **gasto mensual de referencia de un hogar** de
su jurisdicción —una estimación declarada, con año y fuente—, así que un
presupuesto se puede leer como «tantos meses de gasto doméstico». Un territorio
sin ese dato no recibe cifras inventadas: sus clubes salen con importes sin
determinar.

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
- No hay grupos, divisiones ni conferencias: toda competición es una tabla
  única. Vincular dos competiciones sí funciona; dividir una por dentro, no.
- **No hay mapa.** La geografía se busca y se consulta como texto, que es lo
  accesible; no hay vista cartográfica ni polígonos descargados.
- **El coste de referencia solo está curado para cinco países.** Se conoce la
  moneda de 251 de 252, pero los importes solo se pueden calcular en México,
  Argentina, Brasil, Cuba y República Dominicana. En el resto del mundo los
  mundos se generan sin cifras económicas, declarado como tal.
- La escala económica profesional está por debajo de la realidad: faltan
  derechos de televisión nacionales, traspasos y explotación comercial. No se
  finge ninguno; se nota en que un club profesional sale más modesto de lo que
  sería.
- Al ascender o descender se reescala el presupuesto y se mueve la reputación,
  nada más: no hay renegociación de contratos ni ajuste de plantilla.
- La economía no está calibrada contra nada: los presupuestos son heurísticas, y
  también lo son las tasas de cobro del cierre de temporada (80–99 % de las
  cuotas, 55–100 % del patrocinio, 8 % de incumplimiento). Lo garantizado es que
  cobrar no es presupuestar, no el decimal exacto.
- Un club puede desaparecer, pero dos clubes no se fusionan y uno desaparecido
  no se refunda.
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
- [Gazetteer](data/gazetteer/README.md) — GeoNames y geoBoundaries: licencias, atribución y qué no aportan
- ADR: [monolito modular](docs/adr/0001-modular-monolith.md) ·
  [persistencia dual](docs/adr/0002-persistencia-dual-y-gis-diferido.md) ·
  [RNG por contexto](docs/adr/0003-rng-derivado-por-contexto.md) ·
  [frontera de temporada y autoridad de la cuota](docs/adr/0004-frontera-de-temporada-y-autoridad-de-la-cuota.md) ·
  [economía bottom-up y modalidad reglamentaria](docs/adr/0005-economia-bottom-up-y-modalidad-reglamentaria.md) ·
  [gazetteer mundial](docs/adr/0006-gazetteer-mundial-geonames.md) ·
  [liquidación de temporada y vida institucional](docs/adr/0007-liquidacion-de-temporada-y-vida-institucional.md)

## Licencias y atribución

El fixture geográfico usa nomenclatura y centroides públicos; si se amplía con
datos de OpenStreetMap, aplican su
[licencia y atribución](https://www.openstreetmap.org/copyright) y su
[política de tiles](https://operations.osmfoundation.org/policies/tiles/).
Todo lo demás —clubes, personas, escudos, estadios, empresas— es ficticio y
generado por el motor.
