#!/usr/bin/env bash
# Comprueba el stack por el MISMO camino que usa el navegador: todo contra el
# origen del frontend, nunca contra la API directamente.
#
# Esta prueba existe porque una vez se dio por bueno el stack comprobando
# `GET /` del frontend (200) y `GET /health` de la API (200), sin comprobar que
# las llamadas de la interfaz llegaran a la API. No llegaban: el proxy de `/api`
# solo existía en el modo de desarrollo de Vite. De ahí un 404 en cada pantalla.
set -euo pipefail

FRONT="${FRONT:-http://127.0.0.1:5173}"
fallos=0

comprobar() {
  local descripcion="$1" esperado="$2" obtenido="$3"
  if [[ "$obtenido" == "$esperado" ]]; then
    printf '  ok    %-44s %s\n' "$descripcion" "$obtenido"
  else
    printf '  FALLO %-44s esperado %s, obtenido %s\n' "$descripcion" "$esperado" "$obtenido"
    fallos=$((fallos + 1))
  fi
}

codigo() { curl -s -o /dev/null -w '%{http_code}' -m 20 "$@"; }

echo "comprobando el stack a través de $FRONT"

# `docker compose up -d` vuelve cuando el contenedor arrancó, no cuando Node ya
# escucha. Se espera con un tope, en vez de asumir que está listo.
for intento in $(seq 1 40); do
  if curl -s -o /dev/null -m 3 "$FRONT/" 2>/dev/null; then break; fi
  if (( intento == 40 )); then
    echo "  FALLO el frontend no respondió en 80 s; revisa 'docker compose logs frontend'"
    exit 1
  fi
  sleep 2
done

comprobar "la página de universos carga"        200 "$(codigo "$FRONT/")"
comprobar "la API responde por el mismo origen" 200 "$(codigo "$FRONT/api/v1/universes")"

creado=$(curl -s -m 30 -X POST "$FRONT/api/v1/universes" \
  -H 'content-type: application/json' \
  -d '{"name":"Humo '"$RANDOM"'","world_date":"2042-03-20","master_seed":4242}')
universo=$(printf '%s' "$creado" | sed -n 's/.*"id":"\([a-f0-9]*\)".*/\1/p')

if [[ -z "$universo" ]]; then
  echo "  FALLO crear universo: $creado"
  exit 1
fi
printf '  ok    %-44s %s\n' "crear universo" "${universo:0:8}"

comprobar "la ficha del universo carga"   200 "$(codigo "$FRONT/universos/$universo")"
comprobar "el panel trae datos"           200 "$(codigo "$FRONT/api/v1/universes/$universo/dashboard")"
comprobar "la geografía trae datos"       200 "$(codigo "$FRONT/api/v1/universes/$universo/geography")"
comprobar "el asistente de liga previsualiza" 200 "$(codigo -X POST \
  "$FRONT/api/v1/universes/$universo/competitions/preview" \
  -H 'content-type: application/json' \
  -d '{"name":"Liga de humo","kind":"municipal_league","scope":{"level":"municipal","country_code":"MX","place_keys":["MX-CJS"]},"season":{"games_per_club_target":22},"generation":{"club_count":6,"seed":1}}')"
comprobar "un 404 real sigue siendo 404"  404 "$(codigo "$FRONT/api/v1/universes/noexiste")"

# El usuario configura la competición, no los clubes: un campo de riqueza se
# rechaza con su código propio, aunque venga por la API a mano.
rechazo=$(curl -s -m 30 -X POST "$FRONT/api/v1/universes/$universo/competitions" \
  -H 'content-type: application/json' \
  -d '{"name":"Liga prohibida","kind":"municipal_league","scope":{"level":"municipal","country_code":"MX","place_keys":["MX-CJS"]},"season":{"games_per_club_target":20},"playoffs":{"slots":0,"format":"none"},"generation":{"club_count":4,"economy":"professional"}}')
if printf '%s' "$rechazo" | grep -q 'DEPRECATED_CLUB_GENERATION_FIELD'; then
  printf '  ok    %-44s %s\n' "el selector de riqueza se rechaza" "DEPRECATED_CLUB_GENERATION_FIELD"
else
  printf '  FALLO %-44s %s\n' "el selector de riqueza se rechaza" "$rechazo"
  fallos=$((fallos + 1))
fi

# Geografía mundial: el gazetteer responde y resuelve fuera del fixture.
geo=$(curl -s -m 20 "$FRONT/api/v1/geography/status")
if printf '%s' "$geo" | grep -q '"imported": *true'; then
  entidades=$(printf '%s' "$geo" | sed -n 's/.*"entities": *\([0-9]*\).*/\1/p')
  printf '  ok    %-44s %s entidades\n' "el gazetteer mundial está importado" "$entidades"
  kampala=$(curl -s -m 20 "$FRONT/api/v1/geography/search?q=Kampala&limit=1" |
    sed -n 's/.*"country_iso2": *"\([A-Z]*\)".*/\1/p' | head -1)
  comprobar "buscar «Kampala» resuelve a Uganda" UG "${kampala:-vacío}"
  moneda_ug=$(curl -s -m 20 "$FRONT/api/v1/geography/search?q=Kampala&limit=1" |
    sed -n 's/.*"currency": *"\([A-Z]*\)".*/\1/p' | head -1)
  comprobar "y su moneda es la de su jurisdicción" UGX "${moneda_ug:-vacía}"
else
  printf '  ok    %-44s %s\n' "gazetteer no importado (opcional)" "make import-geonames"
fi

# La moneda sale de la jurisdicción, no de un ajuste global.
moneda=$(curl -s -m 20 "$FRONT/api/v1/universes/$universo/geography" |
  sed -n 's/.*"key": *"MX-CJS"[^}]*"currency": *"\([A-Z]*\)".*/\1/p' | head -1)
comprobar "la moneda la resuelve el territorio" MXN "${moneda:-vacía}"

# Relaciones de ascenso y descenso: se crean dos competiciones de verdad y se
# comprueba que la regla efectiva se lee por el camino del navegador.
crear_liga() {
  curl -s -m 60 -X POST "$FRONT/api/v1/universes/$universo/competitions" \
    -H 'content-type: application/json' -d "$1" |
    sed -n 's/.*"id":"\([a-f0-9]*\)".*/\1/p'
}
superior=$(crear_liga '{"name":"Liga Superior de humo","kind":"national_league","scope":{"level":"national","country_code":"MX","place_keys":["MX"]},"season":{"games_per_club_target":10},"playoffs":{"slots":0,"format":"none"},"generation":{"club_count":4,"seed":1}}')
inferior=$(crear_liga '{"name":"Liga Inferior de humo","kind":"regional_league","scope":{"level":"regional","country_code":"MX","place_keys":["MX-CHH"]},"season":{"games_per_club_target":10},"playoffs":{"slots":0,"format":"none"},"generation":{"club_count":4,"seed":2}}')

if [[ -z "$superior" || -z "$inferior" ]]; then
  echo "  FALLO crear las competiciones de la prueba de ascenso"
  exit 1
fi
comprobar "vincular ascenso y descenso" 201 "$(codigo -X POST \
  "$FRONT/api/v1/competitions/$superior/relationships" \
  -H 'content-type: application/json' \
  -d '{"target_competition_id":"'"$inferior"'","relation_kind":"promotion_relegation","exchange_slots":2}')"

plazas_arriba=$(curl -s -m 20 "$FRONT/api/v1/competitions/$superior/mobility" |
  sed -n 's/.*"exchange_slots": *\([0-9]*\).*/\1/p')
plazas_abajo=$(curl -s -m 20 "$FRONT/api/v1/competitions/$inferior/mobility" |
  sed -n 's/.*"exchange_slots": *\([0-9]*\).*/\1/p')
comprobar "la cuota que ve la liga superior"  2 "$plazas_arriba"
comprobar "la misma cuota que ve la inferior" 2 "$plazas_abajo"
comprobar "el grafo de competiciones carga"   200 "$(codigo "$FRONT/universos/$universo/grafo")"
comprobar "el historial de movilidad carga"   200 "$(codigo "$FRONT/api/v1/universes/$universo/mobility-history")"

comprobar "borrar devuelve 204 sin cuerpo" 204 "$(codigo -X DELETE "$FRONT/api/v1/universes/$universo")"

if (( fallos > 0 )); then
  echo "$fallos comprobación(es) fallida(s)"
  exit 1
fi
echo "stack verificado por el camino del navegador"
