# Fuentes de datos y grado de confianza

## Regla

Cada dato numérico del mundo lleva `confidence` y `sources`. Tres valores:

- `observed` — tomado de una fuente publicada que se cita.
- `estimated` — heurística nuestra a partir de otra cosa. Es una suposición.
- `fictional` — inventado para que el mundo funcione. No describe la realidad.

La interfaz muestra la marca. Un índice `estimated` no se presenta como hecho.

## Fixture actual: `data/fixtures/places.json`

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

- OpenStreetMap, licencia y atribución: https://www.openstreetmap.org/copyright
- Política de uso de tiles de OSM: https://operations.osmfoundation.org/policies/tiles/
- Open-Meteo histórico (futuro, para perfiles estacionales): https://open-meteo.com/en/docs/historical-weather-api

Ninguno de los tres se consulta en tiempo de ejecución hoy.
