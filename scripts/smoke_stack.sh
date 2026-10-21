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
comprobar "borrar devuelve 204 sin cuerpo" 204 "$(codigo -X DELETE "$FRONT/api/v1/universes/$universo")"

if (( fallos > 0 )); then
  echo "$fallos comprobación(es) fallida(s)"
  exit 1
fi
echo "stack verificado por el camino del navegador"
