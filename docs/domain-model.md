# Modelo de dominio — Baseball Universe

Marcas: `[I]` implementado y usado, `[T]` tabla/validación presente pero sin
motor que la consuma todavía, `[P]` planificado sin código.

## 1. Separaciones que el modelo no negocia

| Se separa | De | Por qué |
|---|---|---|
| `CompetitionDefinition` | `CompetitionEdition` | la definición es estable; la edición congela reglas, calendario y participantes |
| `Club` | `EditionEntry` | el club persiste entre temporadas y competiciones; la inscripción es anual |
| `Person` | `RosterAssignment` | la persona es única en el universo; la pertenencia a una plantilla es un intervalo |
| `CompetitionRelationship` | `QualificationPath` | jerarquía (ascenso/descenso) ≠ ruta de cupos a una copa |
| `Place` | `NationalTeam` | un país es territorio; una selección es identidad federativa |

Toda entidad lleva `universe_id`. Ninguna clave externa cruza universos; se
verifica en el servicio y, donde el motor lo permite, con una restricción.

## 2. Entidades implementadas

### Universe `[I]`
`id, name, world_date, master_seed, sim_version, config, status, sim_lock_token, created_at`

Savegame aislado. `world_date` es la fecha del mundo, independiente del reloj
real. `master_seed` es la raíz de toda la aleatoriedad.

### Place `[I]` / RegionProfile `[I]`
`places(id, universe_id, kind, parent_id, name, country_code, timezone, lat, lon, provenance)`
con `kind ∈ {country, region, city, district}`.

`region_profiles(place_id, ref_year, population, economy_index,
baseball_culture_index, cost_of_living_index, infrastructure_index,
confidence, sources)`

`confidence ∈ {observed, estimated, fictional}` y `sources` es una lista de
cadenas. **La UI muestra esa marca**: un índice cultural estimado no se presenta
como dato.

### CompetitionDefinition `[I]` / CompetitionRuleVersion `[I]` / CompetitionEdition `[I]`
La definición guarda nombre, `kind`, `scope`, `relationship_mode`
(`independent` por defecto) y el territorio. La versión de reglas guarda el
`RuleSet` validado como JSON más un `checksum`. La edición apunta a **una**
versión de reglas: cambiar reglas no reescribe ediciones cerradas.

`RuleSet` (pydantic, `simulation/competitions/ruleset.py`, esquema **2.0.0**)
cubre hoy: identidad y clase, **modalidad de participación**, territorio,
**elegibilidad** (edad mínima y máxima, corte, salvaguarda de menores,
residencia), **requisitos de admisión** (licencia, certificado de seguridad,
aforo y roster mínimos), **normas económicas** (norma de compensación, tope
salarial, inscripción), temporada (partidos objetivo, series, localías,
descansos, hueco entre temporadas), clasificación, playoffs y generación
(número de clubes, procedencia admitida del talento, semilla).

**Lo que el `RuleSet` no puede expresar, por diseño:** nada que decida el
presupuesto, la propiedad, el personal, la instalación o la riqueza de los
clubes. Esos campos existieron (`generation.professionalization`,
`generation.economy`, `generation.institutional_maturity`) y se eliminaron en el
FIX V2 de Fase 1; la API los rechaza con el código
`DEPRECATED_CLUB_GENERATION_FIELD`. La modalidad es la única pregunta de
naturaleza institucional, y lo que determina son reglas: si se admite pagar a
los jugadores, si se espera licencia y qué carga de calendario se considera
sostenible. Ver `docs/adr/0005-economia-bottom-up-y-modalidad-reglamentaria.md`.

### Club `[I]` / ClubMembership `[I]` / Venue `[I]`
El club es la institución persistente: identidad, marca, tipo institucional,
reputación separada en local/nacional/internacional, finanzas iniciales. Un
descenso o un cambio de competición **no** regenera el club: cambia su
`ClubMembership`.

La pertenencia tiene vigencia por temporadas (`start_season`, `end_season`) y no
solo por edición, porque un ascenso se resuelve cuando la edición de destino
todavía no existe: el club ya es miembro de su nueva competición desde la
temporada siguiente, aunque su calendario se construya después. `origin` dice
cómo entró: `generated`, `promoted` o `relegated`.

### ClubFinancialProfile `[I]` / OrganizationProfile `[I]`
Resultados del generador, nunca entradas del formulario. Se persisten en
`clubs.finance_profile` y `clubs.organization`.

`ClubFinancialProfile` (`simulation/economy/model.py`) distingue a propósito los
conceptos que la especificación pide no confundir: `operating_budget_period`
—el gasto previsto de la temporada, que es lo que se llama «presupuesto»—,
`cash_balance`, `revenue`, `expenses`, `debt`, `assets` y `valuation`, que para
un club llanero normalmente **no existe**. Cada `FinancialComponent` lleva su
`kind` (ingreso o gasto), su `source`, su `basis` en texto, su `confidence` y si
es obligatorio. Un importe puede ser `None`: significa que el concepto existe y
no hay base para cuantificarlo, no que valga cero.

`OrganizationProfile` (`simulation/generation/organization.py`) guarda la forma
de gobierno —de colectivo sin propietario a franquicia—, el acuerdo de sede
—campo público compartido, instalación escolar, alquiler, propia, itinerante— y
el reparto de responsabilidades, donde una persona puede acumular funciones y un
puesto puede quedar vacante. Dos clubes de la misma competición pueden tener
combinaciones distintas: la modalidad inclina la distribución, no la impone.

### ClubSeasonLedger `[I]` / ClubOrganizationChange `[I]`
Lo que de verdad pasó con el dinero y con la institución, temporada a temporada.
`ClubFinancialProfile` **prevé**; esto **liquida**.

`club_season_ledgers(club_id, season, collected, paid, result, cash_start,
cash_end, debt_start, debt_end, outcome, entries, notes)` guarda un asiento por
partida con su importe real y el previsto al lado, para que la diferencia sea
legible: un patrocinio que no se cobró, una taquilla recortada porque faltaron
partidos. `outcome` es `healthy | strained | insolvent`. La clave única
`(club_id, season)` hace **idempotente** la liquidación: reintentar un avance no
cierra dos veces la misma temporada.

`club_organization_changes(club_id, season, field, before, after, reason)` es la
historia institucional: cada cambio de base social, gobierno, sede o alcance con
su causa en texto. No se sobrescribe el pasado.

`clubs.seasons_insolvent` cuenta las temporadas consecutivas sin poder cubrir
obligaciones, y `clubs.status` pasa a `folded` a la segunda. Un club desaparecido
conserva su fila, su historia y sus títulos; deja de competir, no se borra, y ya
no entra en ascensos, descensos ni inscripciones.

### EconomicAnchor `[I]`
Moneda de curso legal y gasto mensual de referencia de un hogar, por
jurisdicción, con año y confianza. Vive en el fixture geográfico y en
`places.economy`. Es el **único** punto del simulador donde un índice relativo
se convierte en un importe, y su ausencia se propaga como
`insufficient_data` en vez de rellenarse con la moneda de otro país.

### Person `[I]` / RosterAssignment `[I]`
Una persona por universo. Atributos en cinco bloques (físico, bateo, pitcheo,
defensa/corrido, cognición) más `potential` oculto y `scouted_potential`
observado con error. La nacionalidad no otorga calidad: el contexto afecta las
**oportunidades de formación** (`training_opportunity`), no un techo biológico.

### Game `[I]` / GameEvent `[I]` / estadísticas `[I]`
`games` guarda `engine_version` y `seed`. `game_events` guarda la secuencia de
turnos de bateo. `player_game_stats`, `pitcher_game_stats` y `team_game_stats`
son atómicas por partido; los agregados de temporada se calculan por consulta.

**Innings lanzados se guardan en outs enteros** (`outs_recorded`), nunca en
flotante: 6⅓ entradas es `19`, y el ERA se deriva al presentar.

### Standings `[I]`
Fila por `(edition_id, entry_id)` con `wins, losses, ties, points, runs_for,
runs_against, streak`. Se recalcula de forma determinista desde los partidos
terminados; no es un contador que se pueda desincronizar.

### SimulationEvent `[I]` / SimulationCommand `[I]` / SimJob `[I]`
El hecho sucedido, el comando que lo pidió (con `idempotency_key` única) y el
trabajo que lo ejecutó. Repetir un `advance` con la misma clave devuelve el job
original.

### GenerationProvenance `[I]`
`(universe_id, entity_kind, entity_id, procedure, procedure_version, seed,
inputs, assumptions)`. Responde "¿de dónde salió este presupuesto?" con datos,
no con una suposición.

### CompetitionRelationship `[I]` / SeasonTransition `[I]`
`competition_relationships(source_id, target_id, relation_kind, config,
effective_from_season)`. **Autoridad única**: la configuración efectiva vive en
la fila de la relación, no duplicada en cada competición, y `config` es un
`MobilityConfig` tipado y versionado
(`simulation/competitions/mobility.py`), no JSON libre.

Reparto de autoridad dentro de la escalera, para que no existan dos números que
puedan contradecirse:

| Campo | Autoridad |
|---|---|
| `exchange_slots` (cuota **total**), `upper_selection`, `allow_unbalanced`, `budget_adaptation`, `apply_at` | la competición superior; editarlos se propaga a todas sus ramas |
| `branch_slots` (parte de la cuota de esa rama), `lower_selection`, `requirements`, `on_requirement_failure`, `eligibility_policy` | cada rama |

Validaciones activas: no autorreferencia, no ciclo superior/inferior, no dos
superiores para la misma competición, una copa no puede ser eslabón de ascenso,
un torneo de selecciones tampoco, la cuota total es la misma en todas las ramas
y el reparto por rama no puede sumar más que el total.

`season_transitions(upper_competition_id, season, applied_on, plan, promotions,
relegations)` es el libro de cierres aplicados. Su clave única hace idempotente
el intercambio y guarda el plan completo —movimientos, rechazos y notas— para
que el historial pueda explicar cada movimiento.

Los vínculos `affiliate`, `youth` y `development` usan otro schema
(`DevelopmentLinkConfig`) en el que `moves_clubs` es literalmente `False`: una
filial no puede acabar tratándose como una división por un campo mal puesto.

## 3. Entidades con tabla y validación, sin motor `[T]`

- `qualification_paths(source_competition_id, target_competition_id, slot_rule, config)`.
  Crear una ruta **no** cambia `relationship_mode`: una liga independiente que
  manda su campeón a una copa sigue siendo independiente. La extracción de
  participantes es Etapa 3 y no está implementada.

## 4. Planificado `[P]`

`federations`, `national_teams`, `callups`, `sporting_eligibilities`,
`sponsors`, `sponsorship_contracts`, `club_accounts`, `attendance_records`,
`contracts`, `snapshots`.

## 5. Invariantes de integridad vigentes

1. `game.home_score` = suma de carreras de `team_game_stats` del local, y los
   outs del partido son coherentes con las entradas jugadas.
2. Un partido en estado `final` no se vuelve a simular sin política explícita de
   replay (hoy: no existe, se rechaza).
3. Un `advance` con la misma `idempotency_key` no duplica partidos.
4. Una persona no tiene dos `roster_assignments` activos solapados.
5. Toda `CompetitionEdition` referencia una versión congelada de reglas.
6. El JSON de configuración se valida contra schemas tipados versionados; no se
   guarda JSON opaco.
7. Un intercambio de ascenso y descenso no se aplica dos veces para la misma
   temporada: lo impide la clave única de `season_transitions`.
8. Suben tantos clubes como bajan, salvo que el usuario active `allow_unbalanced`
   a propósito. Si un requisito bloquea un ascenso, se pierde también el descenso
   que le correspondía.
9. Ningún club queda inscrito en dos competiciones a la vez: ascender o descender
   cierra la pertenencia anterior en la misma transacción que abre la nueva.
10. El presupuesto de un club es la **suma de sus partidas de gasto**
    justificadas, y ninguna de ellas se deriva de la modalidad de la
    competición. Hay pruebas que fallan si alguien reintroduce un camino de
    etiqueta a importe.
11. Un importe solo existe si existe el ancla monetaria de su jurisdicción. Sin
    ancla, `None` y `insufficient_data`; nunca una cifra inventada.
12. La edad de una persona se mide en la **fecha de corte del reglamento**, no en
    el día que toque: con corte al inicio de temporada, quien cumple años en
    octubre juega toda la temporada en la categoría que tenía en marzo.
13. Una temporada no se liquida dos veces para el mismo club: lo impide la clave
    única de `club_season_ledgers`. La caja y la deuda de un club son siempre
    las que dejó su último cierre.
14. Una obligación de la temporada se paga entera, con caja o con deuda. Lo que
    no se puede cubrir se convierte en deuda y se dice; no se perdona para que
    cuadre el balance, y no se inyecta dinero a un club para mantener el número
    de equipos de una liga.
15. Un club desaparece solo tras **dos** temporadas consecutivas insolventes, y
    su desaparición queda registrada como hecho con su causa y su cifra.
