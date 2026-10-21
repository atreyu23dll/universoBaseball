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

`RuleSet` (pydantic, `simulation/competitions/ruleset.py`) cubre hoy:
estructura (número de clubes, grupos), temporada (partidos objetivo, balance de
localías, días de descanso), clasificación (criterio primario + desempates),
playoffs (plazas, longitudes de serie) y generación (profesionalización,
economía, origen del talento, semilla).

### Club `[I]` / ClubMembership `[I]` / Venue `[I]`
El club es la institución persistente: identidad, marca, tipo institucional,
reputación separada en local/nacional/internacional, finanzas iniciales. Un
descenso o un cambio de competición **no** regenera el club: cambia su
`ClubMembership`.

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

## 3. Entidades con tabla y validación, sin motor `[T]`

- `competition_relationships(source_id, target_id, relation_kind, config, effective_from)`.
  **Autoridad única**: la configuración efectiva vive en la fila de la relación,
  no duplicada en cada competición. Validaciones ya activas: no autorreferencia,
  no ciclo superior/inferior, `exchange_slots ≥ 1`, una copa no puede ser eslabón
  de ascenso. Lo que falta es el intercambio al cerrar temporada.
- `qualification_paths(source_competition_id, target_competition_id, slot_rule, config)`.
  Crear una ruta **no** cambia `relationship_mode`: una liga independiente que
  manda su campeón a una copa sigue siendo independiente.

## 4. Planificado `[P]`

`federations`, `national_teams`, `callups`, `sporting_eligibilities`,
`sponsors`, `sponsorship_contracts`, `ledger_entries`, `club_accounts`,
`attendance_records`, `contracts`, `snapshots`.

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
