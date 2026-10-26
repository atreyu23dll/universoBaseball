# Catálogo mundial de instituciones de educación superior

Lo que decide cuántos equipos tiene una liga escolar de 18 años o más. Si en
el territorio hay cinco instituciones reales, juegan cinco: este fichero es de
dónde salen.

| Ruta | Qué es | ¿Versionado? |
|---|---|---|
| `universities.ndjson.gz` | 27 268 instituciones de 206 países, una por línea: identificador de Wikidata, nombre, país, coordenadas y, cuando la fuente los publica, clase de centro, año de fundación y web (1 MB) | **Sí** |
| `MANIFEST.json` | Con qué criterio y qué día se generó, y cuántas instituciones y países trae | **Sí** |

## Por qué está aquí dentro y no se descarga

El catálogo anterior se sacaba del volcado completo de GeoNames: 422 MB
comprimidos y 1,8 GB en disco que la API descargaba al arrancar, para acabar
con 1 534 universidades repartidas de forma muy desigual —27 en todo México—.
Ahora el fichero viaja con el repositorio y **nada se descarga en tiempo de
ejecución**: ni al consultar un territorio, ni al crear una liga, ni al
simular una temporada.

## Fuente, licencia y atribución

- Origen: [Wikidata](https://www.wikidata.org), consultado con su servicio
  público SPARQL al generar el fichero.
- Licencia: **CC0 1.0**. No exige atribución; se registra igualmente en cada
  institución importada (`licence`, `source_url`) y en la interfaz.
- Cada registro conserva su QID, así que se puede comprobar en
  `https://www.wikidata.org/wiki/<QID>`.

## Regenerarlo

```bash
make build-university-catalog   # consulta Wikidata país por país y reescribe el fichero
make import-universities        # lo carga en la base: esto no usa red
```

El generador lleva escrita la lista de clases que admite y las que descarta
—facultades, academias de ciencias, escuelas primarias mal clasificadas— con
el motivo de cada una. Un campus sí cuenta como institución aparte.

## Qué no es

No es un ranking ni un censo oficial. Es lo que Wikidata publica con
coordenadas, que basta para situar una institución en un territorio y darle un
nombre real a un equipo. La provincia y el municipio de cada una **no** salen
de aquí: los resuelve el importador contra el gazetteer, buscando la localidad
real más cercana.
