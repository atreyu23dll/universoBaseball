# Fuentes de datos y grado de confianza

## Regla

Cada dato numérico del mundo lleva `confidence` y `sources`. Tres valores:

- `observed` — tomado de una fuente publicada que se cita.
- `estimated` — heurística nuestra a partir de otra cosa. Es una suposición.
- `fictional` — inventado para que el mundo funcione. No describe la realidad.

La interfaz muestra la marca. Un índice `estimated` no se presenta como hecho.

## Dos fuentes, dos papeles

| Fuente | Qué aporta | Papel |
|---|---|---|
| **GeoNames** (`data/gazetteer/`) | 252 países con su moneda ISO 4217, 3 865 divisiones administrativas, 236 632 localidades con variantes de nombre, coordenadas, altitud y población | **Fuente principal**: cobertura mundial |
| **Fixture curado** (`data/fixtures/places.json`) | 25 lugares con índices de economía, cultura beisbolística, coste e infraestructura calibrados a mano, y el ancla monetaria de cinco países | Los lugares cuyos índices hemos calibrado |

El fixture dejó de ser el catálogo del mundo. Lo que aporta ahora es
**calibración**: cuando un lugar del gazetteer coincide con uno curado, se
reutilizan sus índices en vez del supuesto neutral.

Licencias y atribución del gazetteer: ver `data/gazetteer/README.md`.

### Lo que un gazetteer no puede dar

GeoNames da identidad, jerarquía, coordenadas, altitud, población y moneda. No
da economía local, cultura beisbolística ni infraestructura deportiva. Para un
territorio no curado, esos índices salen con confianza
**`scenario_assumption`** y valor neutral (0.5), y la interfaz lo dice.

No se deducen del país. Que Uganda no tenga tradición beisbolística documentada
no se infiere de su bandera: se declara que no hay evidencia y se invita a
calibrarlo. Lo contrario sería un estereotipo presentado como dato.

## Fixture curado: `data/fixtures/places.json`

Contiene México (país), tres estados y ocho ciudades, más subzonas sintéticas
para Ciudad Juárez.

| Campo | Confianza | Nota |
|---|---|---|
| Nombre, país, código ISO, huso horario | `observed` | Nomenclatura pública estándar |
| Latitud / longitud (centroide) | `observed` | Centroides aproximados de ciudad, redondeados |
| Población | `estimated` | Orden de magnitud con `ref_year` declarado. **No** es un censo: sirve para escalar mercados, no para citar cifras |
| `economy_index`, `cost_of_living_index` | `estimated` | Escala relativa 0–1 definida por nosotros |
| `baseball_culture_index` | `estimated` | Calibrable por el usuario. **No** se infiere del país como si fuera un rasgo nacional: es un parámetro del mercado |
| `infrastructure_index` | `estimated` | Proxy de instalaciones disponibles |
| Subzonas de Ciudad Juárez | `fictional` | Áreas sintéticas etiquetadas como tales; no son colonias reales |
| Estadios | `fictional` | Todos los recintos generados son ficticios |
| Moneda del país (`economy.currency`) | `observed` | Código ISO 4217 de curso legal |
| Gasto mensual de referencia (`economy.reference_monthly_cost`) | `estimated` | **Orden de magnitud** del gasto mensual de un hogar, con año declarado. Es el único punto donde los índices relativos se convierten en importes |

## El ancla monetaria y por qué existe

Los índices del perfil regional son relativos (0–1) y no pueden producir
dinero por sí solos. Cada país del fixture declara una **ancla**: su moneda de
curso legal y un gasto mensual de referencia de un hogar, estimado y fechado.

Todo importe que el simulador calcula es un múltiplo de esa ancla, así que
cualquier presupuesto se puede leer como «tantos meses de gasto doméstico». Eso
hace la cifra discutible: se puede decir «cuatro meses de gasto de un hogar para
una temporada de un club de barrio es poco/mucho», que es una conversación
posible, en vez de aceptar un número caído del cielo.

**Un territorio sin ancla no recibe cifras inventadas.** Sus clubes salen con
importes `null` y confianza `insufficient_data`, y la interfaz dice «sin
determinar». Es la regla de V2 §7.2: antes un hueco declarado que falsa
precisión.

## Las tasas de cobro del cierre de temporada

Liquidar una temporada exige decidir **cuánto de lo previsto se cobra de verdad**
(`simulation/economy/season_close.py`). Esos rangos no salen de ninguna fuente:
son heurísticas declaradas, y están en una constante con nombre
(`COLLECTION_RATES`) para que se vean y se puedan discutir.

| Fuente de ingreso | Se cobra |
|---|---|
| Cuotas de socios | 80–99 % |
| Patrocinio local | 55–100 %, y un 8 % de probabilidad de incumplimiento total |
| Taquilla | 90–100 %, **por los partidos jugados en casa**, no los programados |
| Apoyo institucional | 70–100 % |
| Respaldo privado | 85–100 % |
| Donaciones | 60–100 % |

Lo que estos números garantizan es una afirmación cualitativa: **cobrar no es
presupuestar**, y un patrocinio prometido no es dinero en caja (V2 §7.1). El
decimal exacto no está calibrado contra nada y se puede mover sin que cambie
ninguna conclusión del simulador. El interés de la deuda (12 % anual) y la
amortización (25 % de la caja disponible) son del mismo tipo.

Lo que **no** es heurística: una obligación se paga entera y lo que no se puede
cubrir se convierte en deuda. Esa es una regla, no un parámetro.

## Universidades: Wikidata, versionado y sin red

Las ligas escolares de 18 años o más juegan con **instituciones reales**: si en
el territorio hay cinco, juegan cinco. Ese catálogo sale de **Wikidata**
(CC0 1.0, sin exigencia de atribución, que igualmente se registra) y vive en
`data/universities/universities.ndjson.gz`, versionado con el repositorio.

| | antes | ahora |
|---|---|---|
| Origen | `allCountries.zip` de GeoNames | Wikidata, consultado una vez al generar el fichero |
| Qué se descargaba al arrancar | 422 MB comprimidos, 1,8 GB en disco | **nada** |
| Instituciones en el mundo | 1 534 | **27 268** en 206 países |
| En México | 27 | **254** |
| Tamaño en disco | 2,1 GB en un volumen de Docker | 1 MB versionado |

Dos reglas que no se rompen:

1. **Nada de red en tiempo de ejecución.** Ni al consultar un territorio, ni al
   crear la liga, ni al generar la edición. El fichero se regenera a mano con
   `make build-university-catalog`, que es el único punto que habla con
   Wikidata, y `make import-universities` solo lee el fichero.
2. **El territorio lo pone el gazetteer, no la fuente educativa.** Wikidata da
   nombre, clase y coordenadas; la provincia, el municipio y el huso horario
   salen de la localidad real más cercana del gazetteer. Si no hay ninguna a
   menos de 60 km, la institución se guarda sin división administrativa en vez
   de adjudicarle una: la búsqueda por radio sigue encontrándola por sus
   coordenadas.

### Qué cuenta como institución, y qué no

El árbol «institución de educación superior» de Wikidata no sirve tal cual:
cuelgan de él casi diez mil escuelas primarias mal clasificadas, las academias
de ciencias —que son corporaciones de académicos, no centros de enseñanza— y
las **facultades**, que son partes de una universidad. Sin filtrar, una sola
universidad aportaría veinte equipos a una liga.

Por eso `scripts/build_university_catalog.py` lleva la lista explícita de
clases admitidas y excluidas, con su motivo escrito al lado. Un campus **sí**
es institución aparte —el Tec de Monterrey campus Juárez juega contra el campus
Chihuahua—, así que la relación «parte de» no decide: decide la clase.

El criterio prefiere que falte una institución rara a meter en una liga a una
escuela primaria, y el fichero `MANIFEST.json` que acompaña al catálogo deja
constancia de con qué criterio y qué día se generó.

## El dibujo del globo no es una fuente de datos

El selector territorial del creador de competiciones es un globo terráqueo, y
los contornos de los países que dibuja salen de **Natural Earth** (dominio
público) en la versión TopoJSON del paquete `world-atlas`, que viaja con el
frontend y no se descarga en tiempo de ejecución. Ese atlas hace dos cosas, y
ninguna es aportar datos al mundo simulado:

1. **Dibujar.** Es geometría para pintar, no información sobre un lugar.
2. **Resolver un clic.** Cada polígono lleva su código ISO 3166-1 numérico; el
   clic se traduce a alfa-2 y con ese código se le pregunta al gazetteer por la
   entidad. Lo que se fija en la competición sigue siendo el identificador de
   GeoNames, nunca el nombre ni la forma del atlas.

De ahí se siguen dos consecuencias que la interfaz no esconde:

- Los tres territorios del atlas **sin código ISO** —Kosovo, Somalilandia y el
  norte de Chipre— no son seleccionables, y al pasar por encima se dice por qué.
  Antes que asignarles una identidad discutible, se dice que no la hay.
- Provincias y localidades **no se dibujan como contornos**, porque no tenemos
  sus polígonos: son puntos sobre la coordenada que el backend declara
  representativa (`map_anchor`, normalmente su localidad más poblada). Un punto
  no finge una frontera que no está en la fuente.

## Lo que deliberadamente no hacemos

- No geocodificamos en masa contra servicios públicos ni descargamos tiles de
  OpenStreetMap a granel: el mundo arranca desde el fixture local y funciona sin
  red. Un adaptador intercambiable (`simulation/geography/provider.py`) permite
  sustituir la fuente sin tocar el motor.
- No usamos nombres, escudos ni patrocinadores reales. Clubes, personas y
  empresas son ficticios y generados.
- No afirmamos tener pronóstico meteorológico de fechas futuras. El clima se
  construye desde un perfil estacional por latitud/altitud con aleatoriedad
  reproducible, y está marcado como modelo, no como observación.
- La distancia entre ciudades es haversine en línea recta. **No es** tiempo de
  viaje; donde la usamos para fatiga lo decimos.

## Fuentes consultadas para la forma de los datos

- Wikidata, licencia CC0 1.0: https://www.wikidata.org/wiki/Wikidata:Licensing
- Natural Earth, dominio público: https://www.naturalearthdata.com/about/terms-of-use/
- `world-atlas` (TopoJSON de Natural Earth): https://github.com/topojson/world-atlas
- OpenStreetMap, licencia y atribución: https://www.openstreetmap.org/copyright
- Política de uso de tiles de OSM: https://operations.osmfoundation.org/policies/tiles/
- Open-Meteo histórico (futuro, para perfiles estacionales): https://open-meteo.com/en/docs/historical-weather-api

Al producto llegan empaquetados el atlas de Natural Earth (con el frontend) y
el catálogo de Wikidata (con el repositorio): ninguna de estas fuentes se
consulta por red en tiempo de ejecución.
