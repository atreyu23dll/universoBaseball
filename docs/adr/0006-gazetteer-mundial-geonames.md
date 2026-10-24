# ADR 0006 — Gazetteer mundial con GeoNames, y qué hacer con lo que no se sabe

- **Fecha:** 22 de octubre de 2026
- **Estado:** aceptado e implementado
- **Contexto:** FIX V2 de Fase 1, fase P2
- **Decisión del usuario:** GeoNames local + PostgreSQL/PostGIS + geoBoundaries

## Problema

La Fase 1 resolvía el territorio con `data/fixtures/places.json`: 25 entradas,
11 ciudades, 5 países. Elegir «México» ofrecía tres ciudades. Kampala no
existía. El FIX V2 §4.1 lo prohíbe expresamente —«no usar una lista local fija
como fuente principal»— y el criterio de éxito del documento (§20) es que se
pueda crear una liga llanera en Kampala.

Hay dos problemas distintos dentro de ese, y conviene no confundirlos:

1. **Cobertura**: poder nombrar cualquier lugar del mundo.
2. **Conocimiento**: saber algo útil de ese lugar. Un gazetteer da identidad,
   jerarquía, coordenadas y población. **No** da economía local, cultura
   beisbolística ni infraestructura deportiva.

## Decisión

### 1. GeoNames como fuente principal, importado localmente

Se importan los ficheros descargables oficiales: `countryInfo.txt` (252 países
con su **moneda ISO 4217**), `admin1CodesASCII.txt` y `admin2Codes.txt`
(divisiones administrativas) y `cities500.txt` (**236 632 localidades** de 500
habitantes o más, con sus variantes de nombre). Son ~17 MB comprimidos y la
importación tarda unos minutos.

Licencia **CC BY 4.0**, que exige atribución: se guarda en cada entidad
(`source`, `source_id`) y la interfaz la muestra.

Por qué importar en vez de consultar un servicio: el producto es local-first.
Una vez importado, resolver «Kampala» no necesita red, y no se bombardea el
servicio público de nadie. El FIX V2 §18 además descarta expresamente usar el
Nominatim público para autocompletar.

### 2. Identificador propio + referencia externa estable

`gazetteer_entities.id` es nuestra clave; `(source, source_id)` es la referencia
externa —el `geonameid`—. Las competiciones guardan **nuestro** id, así que
cambiar de proveedor no rompe los universos existentes, y reimportar actualiza
por `source_id` sin duplicar.

### 3. El gazetteer es global; el universo tiene su copia

El mundo es el mismo para todas las partidas, así que el gazetteer es
compartido. Pero cada universo mantiene su propia geografía —para poder
calibrar los índices de un mercado sin tocar las demás partidas—, y al crear una
competición se **materializan** las entidades elegidas en ese universo, con sus
ancestros, su población y el ancla monetaria de su país.

### 4. Un texto no es un territorio

El estado de resolución recorre `unresolved → candidates → user_selected →
verified | incomplete`. La búsqueda devuelve **candidatos** desambiguados por
país, jerarquía y tipo de entidad; el usuario elige uno; la competición guarda
el identificador. Un nombre escrito a mano se rechaza con
`GEOGRAPHY_UNRESOLVED` y un mensaje que dice dónde buscar.

### 5. Lo que no se sabe se declara, no se rellena

Esta es la parte que importa más, y la que distingue cobertura de conocimiento:

| Dato | Para Kampala | Confianza |
|---|---|---|
| Identidad, jerarquía, coordenadas | Uganda · Central Region · Kampala District | `observed` |
| Población | 1 680 600 | `observed`, con `geonameid` |
| Moneda | UGX | `observed`, ISO 4217 |
| Coste mensual de referencia | **no hay** | → importes sin determinar |
| Economía, cultura beisbolística, infraestructura | **no hay evidencia** | `scenario_assumption`, 0.5 neutral |

Consecuencia: una liga llanera en Kampala **se genera** —clubes con formas de
gobierno heterogéneas, sedes, plantillas, calendario, partidos y clasificación—
y sus cuentas salen con `insufficient_data` y los conceptos declarados pero sin
cifras. Es literalmente el ejemplo de respuesta del documento (§10.2) y su
regla (§7.2): antes un hueco declarado que falsa precisión.

El índice de cultura beisbolística **no se deduce del país**. Que Uganda no
tenga tradición documentada no se infiere de su bandera: se marca como supuesto
neutral y se avisa de que conviene calibrarlo (§5 y §9.2).

Se añaden dos valores a `Confidence` para poder decir esto:
`scenario_assumption` (supuesto declarado) y `missing` (el dato no existe).

### 6. Los índices curados ganan al supuesto

Si el universo ya tiene un lugar calibrado a mano equivalente —mismo nombre
normalizado y mismo país—, la materialización **reutiliza sus índices**. Buscar
una ciudad en el gazetteer no puede dar peores datos que tenerla en el fixture.

### 7. Límites administrativos: solo donde la fuente los publica

geoBoundaries publica licencia por país —muchos límites derivan de
OpenStreetMap y están bajo ODbL—, así que la tabla `gazetteer_boundaries` guarda
geometría, CRS (`EPSG:4326`), licencia, fuente y año de representación. Se
piden **por territorio y con caché**, no en bloque.

Sin polígono no se dibuja ninguno: el territorio se delimita por **contención
administrativa** —que es exacta, porque GeoNames da los códigos de división de
cada localidad— o por **radio** desde el centroide, declarado como aproximación
en línea recta que no respeta fronteras. Ese es el «informa de ello y ofrece una
delimitación alternativa» del encargo.

## Consecuencias

- **Búsqueda sin PostGIS ni trigramas obligatorios.** El índice GIN de
  trigramas se crea en PostgreSQL si `pg_trgm` está disponible; si no, se degrada
  a búsqueda por prefijo sobre un texto normalizado. Un arranque en SQLite
  funciona igual, más despacio. No se exige una extensión para poder jugar.
- **Las variantes de nombre son una sola columna**, normalizada sin acentos, en
  vez de una tabla de millones de filas. Permite encontrar «Mexico City»
  escribiendo «Ciudad de México» y buscar sin acentos, al precio de no poder
  filtrar por idioma de la variante. Aceptado.
- **El volcado completo no se versiona**: 43 MB de datos de terceros se
  descargan con `make import-geonames`. El repositorio lleva un extracto de 372
  KB —nueve países, 542 localidades— para pruebas y arranque sin red.
- **El fixture curado sigue existiendo**, con otro papel: ya no es el catálogo
  del mundo, es el conjunto de lugares cuyos índices hemos calibrado a mano.
- **El ancla monetaria solo está curada para cinco países.** Los otros 246
  conservan su moneda y generan mundos sin importes. Ampliar esa lista es
  trabajo de datos, no de código, y cada entrada necesita una fuente.

## Alternativas descartadas

- **Autocompletar contra el Nominatim público de OSM.** Prohibido por su política
  de uso y por el propio FIX V2 §18.
- **Autoalojar Photon o Pelias.** Un contenedor más y varios GB de índice para
  un producto que cabe en un portátil. GeoNames importado da la misma cobertura
  de nombres para este caso de uso.
- **Deducir los índices socioeconómicos del país o del continente.** Es
  exactamente el estereotipo que el documento prohíbe (§5, §7.3.6). Mejor un
  supuesto neutral declarado que una inferencia que parece un dato.
- **Descargar geoBoundaries en bloque (CGAZ).** Cientos de MB para dibujar
  polígonos que hoy no se usan para nada más que un mapa que todavía no existe.
  Se pide por territorio cuando haga falta.
