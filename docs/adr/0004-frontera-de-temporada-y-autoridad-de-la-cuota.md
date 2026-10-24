# ADR 0004 — Frontera de temporada y autoridad de la cuota de intercambio

- **Fecha:** 21 de octubre de 2026
- **Estado:** aceptado e implementado
- **Contexto:** Etapa 2, movilidad de clubes entre competiciones vinculadas

## Problema

Tres decisiones estaban abiertas al implementar el ascenso y el descenso:

1. **¿Dónde vive la cuota de plazas?** La especificación exige que las dos
   competiciones muestren siempre la misma regla efectiva y que, con varias
   ligas alimentadoras, la cuota sea un total y no `N` por rama.
2. **¿Cuándo se mueve un club?** Una edición de la liga superior puede terminar
   días antes que la de la inferior.
3. **¿Quién abre la temporada siguiente?** Sin temporada siguiente no hay nada
   que el ascenso pueda cambiar, pero generarla antes del intercambio significa
   construir un calendario con los participantes equivocados.

## Decisión

### 1. La cuota vive en la relación, repartida por autoridad

`competition_relationships.config` guarda un `MobilityConfig` tipado. Los
campos se reparten así:

- **De la competición superior**, iguales para toda la escalera:
  `exchange_slots` (la cuota **total**), `upper_selection`, `allow_unbalanced`,
  `budget_adaptation`, `apply_at`. Editarlos por `PATCH` los propaga a todas las
  ramas en la misma transacción.
- **De cada rama**: `branch_slots` (su parte del total), `lower_selection`,
  `requirements`, `on_requirement_failure`, `eligibility_policy`.

Así ningún hecho está guardado dos veces. `branch_slots` podría haberse guardado
como un diccionario `{competición: plazas}` replicado en cada fila, y se
descartó justamente por eso: habría dos copias que pueden discrepar.

Al **crear** una rama con una cuota total distinta a la de sus hermanas, la API
rechaza con un error explicativo en vez de propagar en silencio: crear algo con
un número equivocado es un malentendido del usuario, no una edición. Al
**editar**, propaga, porque editar es justo la operación que debe mantenerlas
sincronizadas.

### 2. El intercambio espera a toda la escalera

La frontera de temporada se cruza cuando **todas** las competiciones vinculadas
han cerrado la misma temporada. Mientras alguna siga jugando, nadie se mueve y
ninguna de las dos abre temporada nueva. La liga de arriba no puede tener
calendario antes de saber quién sube.

Si una competición de la escalera no ha generado ninguna edición, no bloquea a
las demás: no se puede esperar indefinidamente por una liga que el usuario
vinculó y nunca puso en marcha.

### 3. El mundo abre la temporada siguiente

Ocurre dentro del avance del día, en la misma transacción que cerró la edición,
con los clubes que ya pertenecen a la competición. **No se regenera nada**: ni
clubes, ni personas, ni estadios. Lo único que se construye es el calendario, y
su semilla se deriva por contexto (`derive_seed(master_seed, "edition",
competition_id, season)`), de modo que el orden de las jornadas cambia de un año
a otro sin dejar de ser reproducible.

`universe.config.auto_new_season = false` lo desactiva: los ascensos y descensos
se siguen resolviendo, pero el calendario nuevo no se construye hasta que
alguien lo pida.

## Consecuencias

- **Cambia el contrato de `until_season_end`.** Ya no puede significar «hasta que
  no queden partidos pendientes», porque eso no vuelve a ocurrir nunca: el avance
  apunta las ediciones abiertas al empezar y para cuando todas han terminado.
- **La pertenencia necesita temporadas, no solo ediciones.** `club_memberships`
  gana `start_season`, `end_season` y `origin`; sin eso no se puede expresar
  «este club juega arriba a partir del año que viene» antes de que exista la
  edición de destino.
- **Idempotencia explícita.** `season_transitions(upper_competition_id, season)`
  con clave única. Es la misma estrategia que `simulation_commands`: el libro de
  lo ya hecho, no un `if` que mire el estado.
- **Balance antes que plazas.** Si un requisito de ascenso bloquea una plaza,
  tampoco desciende nadie por ella. La alternativa —descender a alguien sin que
  suba nadie— cambiaría el tamaño de las competiciones por un efecto secundario.
- **El presupuesto se mueve, el club no cambia.** Al cambiar de categoría se
  reescala el presupuesto una fracción (`budget_adaptation`, por omisión 0.5)
  hacia el factor de liga de la nueva competición, usando la **misma** función
  que la generación (`context.league_budget_factor`), y se anota la procedencia.
  Es una heurística sin calibrar y está declarada como tal. No se tocan la caja,
  la deuda, los contratos ni la plantilla: eso es Etapa 4.

## Alternativas descartadas

- **Aplicar el intercambio cuando cada liga cierre, por separado.** Más simple,
  pero obliga a conocer de antemano los descensos de la superior o a reabrir una
  edición ya creada. Se descartó por eso.
- **Un endpoint manual «cerrar temporada».** Deja el mundo parado esperando al
  usuario, en contra del principio de que el mundo evoluciona solo cuando el
  reloj avanza. Queda disponible el interruptor `auto_new_season` para quien
  prefiera lo contrario.
- **Regenerar los clubes de la competición al abrir temporada.** Prohibido por la
  especificación y por sentido: un club que desciende conserva su identidad, su
  historia y sus deudas.
