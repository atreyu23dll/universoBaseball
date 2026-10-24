# Gazetteer mundial

Esta carpeta contiene los datos geográficos con los que el simulador resuelve
territorios de **cualquier parte del mundo**. Sustituye al catálogo cerrado de
`data/fixtures/places.json`, que queda como fuente **curada** de los pocos
lugares cuyos índices socioeconómicos hemos calibrado a mano.

## Qué hay aquí

| Ruta | Qué es | ¿Versionado? |
|---|---|---|
| `sample/` | Extracto reducido (≈360 KB) para pruebas y arranque sin red: nueve países, sus divisiones de primer nivel, las de segundo de México y Uganda, y 544 localidades | **Sí** |
| `geonames/` | Volcado completo: 252 países, 3 865 divisiones de primer nivel, 236 632 localidades de 500 habitantes o más (≈43 MB) | **No** — se descarga |

## Fuentes, licencias y atribución

### GeoNames — localidades, divisiones administrativas y monedas

- Origen: <https://download.geonames.org/export/dump/>
- Licencia: **Creative Commons Attribution 4.0** (CC BY 4.0). Exige atribución.
- Atribución que el simulador registra en cada entidad importada y muestra en la
  interfaz: `GeoNames (https://www.geonames.org), CC BY 4.0`.
- Ficheros usados: `countryInfo.txt`, `admin1CodesASCII.txt`, `admin2Codes.txt`,
  `cities500.txt`.

De aquí sale la **moneda de curso legal de cada jurisdicción** (código ISO 4217
de `countryInfo.txt`), que es lo que responde «¿en qué moneda opera un club de
este territorio?» sin presumir nada por el idioma de la interfaz.

### geoBoundaries — límites administrativos

- Origen: <https://www.geoboundaries.org/> (API `gbOpen`).
- Licencia: **depende del país**. geoBoundaries publica la licencia de cada
  límite —muchos derivan de OpenStreetMap y están bajo ODbL 1.0— y el simulador
  la guarda en la fila del límite junto con su año y su fuente.
- Se piden **solo los territorios que se usan**, uno a uno y con caché en la
  base: no se descarga el mundo entero ni se bombardea su servicio.
- Si un territorio no tiene límite publicado, **no se dibuja ninguno**: la
  competición se delimita por contención administrativa o por radio desde el
  centroide, y la interfaz dice que no hay polígono disponible.

## Lo que GeoNames no aporta, y qué hace el simulador con ese hueco

GeoNames da identidad, jerarquía, coordenadas, altitud, población y moneda. **No
da** economía local, cultura beisbolística ni infraestructura deportiva. Para
esos índices, un territorio importado del gazetteer recibe un **supuesto neutral
declarado** (`scenario_assumption`, valor 0.5) en vez de un número inventado o
—peor— de un estereotipo por país: que un territorio no tenga tradición
beisbolística documentada no se deduce de su bandera.

Los índices se pueden calibrar después, y los lugares del fixture curado
conservan los suyos.

Lo mismo con el dinero: la moneda se conoce para 251 de los 252 países, pero el
**coste mensual de referencia** —el ancla que convierte índices en importes—
solo está curado para México, Argentina, Brasil, Cuba y República Dominicana.
Un club de un país sin ancla sale con las cuentas **sin cuantificar**
(`insufficient_data`), que es lo que el FIX V2 §7.2 exige: antes un hueco
declarado que falsa precisión.

## Cómo importar

```bash
# descarga (≈17 MB comprimidos) e importación completa
make import-geonames

# o por partes
python scripts/import_geonames.py --download --source-dir data/gazetteer/geonames
python scripts/import_geonames.py --source-dir data/gazetteer/geonames

# solo unos países, para probar rápido
python scripts/import_geonames.py --source-dir data/gazetteer/sample --only-countries MX,UG
```

La importación es **idempotente**: reimportar actualiza por `(source, source_id)`
y no duplica. La descarga es un paso explícito y aparte; una vez importado, el
simulador funciona sin conexión.
