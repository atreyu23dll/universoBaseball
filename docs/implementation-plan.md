# Plan de implementación — Baseball Universe

## FIX V2 de Fase 1 — prioridad CRÍTICA, por delante de la Etapa 3

Origen: `BASEBALL_UNIVERSE_FASE_1_ADENDA_GEOGRAFIA_FORMULARIO_Y_REALISMO.md`
**versión 2.0**, que sustituye a la adenda anterior y **prevalece** sobre la
especificación maestra en todo lo relativo al formulario de creación, la
economía y la generación de clubes.

Dos defectos observados que este repositorio tiene hoy, medidos, no supuestos:

1. **Catálogo geográfico cerrado.** La única fuente era `data/fixtures/places.json`:
   25 entradas, 11 ciudades, 5 países. No se podía crear una liga en Kampala.
   **Corregido en P2**: gazetteer de GeoNames con 252 países, 3 865 divisiones
   administrativas y 236 632 localidades.
2. **El dinero lo decide una etiqueta.** `club_budget()` multiplica por un factor
   derivado del nivel de liga, así que la mediana de presupuesto de una liga
   municipal de Ciudad Juárez con `contextual_auto` es de **1 876 351 MXN**
   (amateur: 433 794; profesional: 3 553 002). V2 §7.2 lo prohíbe expresamente.
   **Corregido en P3**, y **recalibrado el 24/10/2026** después de que el usuario
   observara que una llanera seguía manejando 136 427 MXN de mediana: hoy son
   **73 969 MXN** (6,2 meses de gasto de un hogar) y la etiqueta no mueve la
   cifra —profesional entre llanera = 1,19×—. El desglose de las seis causas
   está en `docs/simulation-calibration.md` §7 bis.

A eso se añade lo que falta por completo: modalidad de participación como
concepto de la competición, categorías de edad y elegibilidad, salvaguarda de
menores, moneda por jurisdicción, economía con ingresos y gastos trazables,
organización autónoma de cada club y preview con `preview_id`, huella de
intención y errores tipados.

| Fase del fix | Alcance | Estado |
|---|---|---|
| P0 | Inventario y **pruebas que reproducen los defectos** | **Hecho** |
| P1 | Contraer el formulario: modalidad única, elegibilidad, fuera los selectores de riqueza | **Hecho** |
| P2 | Geocodificación mundial, entidades geográficas y estados de resolución | **Hecho** |
| P3 | Economía bottom-up e instituciones heterogéneas y autónomas | **Hecho** |
| P4 | Preview inmutable con huella y confirmación idempotente | **Hecho** |
| P5 | Evolución institucional en el tiempo y encaje con la Fase 2 | **Hecho** |

**P0 (hecho).** 20 pruebas en `simulation/tests/test_v2_fix_defects.py`
(economía, geografía, edades, organización) y `backend/tests/test_v2_contract.py`
(formulario, DTO, preview, geografía, moneda), escritas con `xfail(strict=True)`
para que `make test` siguiera en verde y, en cuanto una empezara a pasar, pytest
obligara a quitarle la marca. Funcionó: al entregar P1 y P3, catorce de ellas
empezaron a pasar y la batería falló hasta que se actualizaron. Las cuatro que
siguen marcadas son todas de geografía mundial, y son el trabajo de P2.

**P1 + P3 (hecho, entregados juntos).** Se entregaron en una sola pieza porque
quitar `generation.professionalization` del DTO sin sustituir antes la economía
habría dejado el presupuesto en manos del índice contextual, que es el caso peor
del defecto 2. Lo implementado:

- `participation_modality` como única pregunta institucional del asistente, con
  su perfil reglamentario (`ModalityProfile`): compensación admitida, licencia
  esperada y carga de calendario sostenible. **Ningún importe depende de ella**,
  y hay una prueba que lo vigila.
- Bloques nuevos de reglamento: `eligibility` (edad mínima y máxima, corte,
  salvaguarda obligatoria con menores, residencia), `admission` (licencia,
  certificado de seguridad, aforo mínimo, roster mínimo) y
  `financial_regulations` (norma de compensación, tope salarial, inscripción).
- Fuera del DTO `generation.professionalization`, `generation.economy` y
  `generation.institutional_maturity`, con rechazo tipado
  `DEPRECATED_CLUB_GENERATION_FIELD` y migración auditable de los reglamentos
  guardados al esquema 2.0.0.
- Paquete `simulation/economy`: componentes de ingreso y gasto con origen, base
  y confianza; recursos locales finitos y disputados entre los clubes de la
  zona; presupuesto como suma de los gastos que el club puede sostener; caja,
  deuda, patrimonio y valoración como conceptos distintos; `insufficient_data`
  cuando la jurisdicción no tiene ancla monetaria.
- `simulation/generation/organization.py`: forma de gobierno, acuerdo de sede y
  reparto de responsabilidades —con funciones acumuladas en una persona y
  puestos vacantes— heterogéneos dentro de la misma competición.
- Ancla monetaria por jurisdicción en el fixture y en la base de datos: la
  moneda sale del territorio y el universo ya no nace en pesos mexicanos.
- Asistente de nueve pasos conforme a V2 §2, ficha de club con el desglose de
  sus cuentas y previsualización que muestra lo que el motor decidió, sin
  ofrecer ningún control para editarlo.

Ver `docs/adr/0005-economia-bottom-up-y-modalidad-reglamentaria.md`.

**P2 (hecho). GeoNames local + PostgreSQL/PostGIS + geoBoundaries.** Lo
implementado:

- Importador de los ficheros oficiales (`scripts/import_geonames.py`, con
  `make import-geonames`): 252 países con su **moneda ISO 4217**, 3 865
  divisiones de primer nivel, 2,4 MB de segundo nivel y **236 632 localidades**
  de 500 habitantes o más con sus variantes de nombre. Idempotente por
  `(source, source_id)`. Atribución CC BY 4.0 registrada en cada entidad.
- Gazetteer **global** en tres tablas (`gazetteer_countries`,
  `gazetteer_entities`, `gazetteer_boundaries`) con índice de trigramas en
  PostgreSQL cuando `pg_trgm` está disponible y degradación a prefijo si no.
- Búsqueda mundial por nombre y variantes, sin acentos, desambiguada por país,
  jerarquía administrativa y tipo de entidad. Una búsqueda sin resultados **no**
  se sustituye por opciones predefinidas.
- Estados de resolución `unresolved → candidates → user_selected → verified |
  incomplete`, y `GEOGRAPHY_UNRESOLVED` cuando alguien manda un nombre a mano
  como territorio.
- Moneda por jurisdicción desde datos territoriales independientes (ISO 4217).
- Delimitación por **radio** cuando no hay polígono administrativo publicado,
  declarada como aproximación en línea recta que no respeta fronteras; y tabla
  de límites con su licencia, CRS y año para cuando geoBoundaries los publique.
- Materialización del territorio elegido en el universo, con sus ancestros, su
  población con fuente y los índices curados cuando el lugar ya estaba
  calibrado; supuesto neutral declarado cuando no.
- Paso 2 del asistente convertido en buscador mundial, con lo que se sabe y lo
  que no de cada territorio elegido.

Ver `docs/adr/0006-gazetteer-mundial-geonames.md`.

**Lo que P2 no resuelve, y se sabe:**

- El **coste mensual de referencia** solo está curado para cinco países. Los
  otros 246 generan mundos completos pero **sin importes**, marcados como datos
  insuficientes. Ampliar la lista es trabajo de datos con fuente, no de código.
- Los **índices socioeconómicos y deportivos** de un territorio no curado son un
  supuesto neutral declarado: no se deducen del país, porque eso sería un
  estereotipo disfrazado de dato.
- **No hay mapa.** La búsqueda es textual y accesible por teclado, que es el
  requisito (§4.1, G07); MapLibre y los polígonos de geoBoundaries descargados
  quedan para cuando haya una vista cartográfica que los use.
- **Los nombres de persona son de español de México.** La marca del club ya
  no: se acuña con morfología propia en español e inglés y con inventario curado
  en ocho idiomas más (ADR 0016), y un país sin gramática curada recibe su
  topónimo verificado. Lo que sigue teniendo un solo idioma es
  `NAME_POOLS`: un jugador de Kampala se llama en castellano. La especificación
  maestra pide «nombre apropiado por contexto lingüístico» (§7.5), así que es
  una deuda real y acotada: hacen falta antropónimos por idioma o región, con
  sus fuentes. Aparece declarada en el propio módulo y en la pantalla
  `/acerca`.

**P4 (hecho). Borrador, previsualización inmutable y confirmación idempotente.**
Lo implementado (`backend/app/application/draft_service.py`):

- **Borrador** con máquina de estados (`draft → previewed → committed`), que
  guarda la intención del usuario tal cual la escribió y nada más.
- `intent_fingerprint`: SHA-256 del JSON canónico de la intención. La
  previsualización queda **inmutable** y atada a esa huella; cambiar cualquier
  cosa del borrador la invalida en vez de mutarla por detrás.
- **La previsualización no escribe nada**: resuelve el territorio en memoria
  (`resolve_ruleset_territory(..., persist=False)`) y devuelve clubes, cuentas,
  calendario y avisos sin crear una fila. Si el usuario no confirma, el universo
  queda exactamente como estaba.
- **Confirmación verificada**: `commit_preview` compara la huella y rechaza con
  409 una previsualización obsoleta o de otra intención, con 422
  `PREVIEW_BLOCKED` si tenía errores que impiden generar. Repetir la misma
  confirmación devuelve la competición ya creada y no genera un segundo mundo
  (`SimulationCommand` como registro de idempotencia).
- **Errores tipados** del catálogo §10.4 (`Issue`), con su campo, su gravedad y
  su explicación; la interfaz los muestra donde se originan.
- 15 pruebas en `backend/tests/test_drafts.py` (T01–T08).

**P5 (hecho). La vida de las instituciones entre temporadas.** Hasta aquí un
club generado era un club congelado: las mismas cuentas cada año. Lo
implementado:

- `simulation/economy/season_close.py`: **liquidación** de la temporada. Lo
  previsto no es lo cobrado —hay socios que dejan de pagar, patrocinadores que
  incumplen (8 % por temporada) y partidos que no se jugaron y no vendieron
  entradas—, mientras que las obligaciones se pagan enteras, con caja o con
  deuda. Intereses del 12 % y amortización del 25 % de la caja disponible.
  Desenlace tipado: `healthy | strained | insolvent`.
- `simulation/economy/evolution.py`: **evolución institucional** con causas
  trazables. La base social se mueve por lo que pasó en el campo, y
  asimétricamente (ganar atrae más de lo que perder aleja); el alcance en la
  zona sube con una temporada sana y baja con las cuentas en rojo; la sede
  mejora si hay caja y ambición y se degrada si no hay para mantenerla; el
  gobierno **se formaliza** con años, arraigo y cuentas sanas, y nunca al revés
  por capricho.
- **Desaparición**: dos temporadas consecutivas sin poder cubrir sus
  obligaciones y el club deja de competir. Conserva su fila, su historia y sus
  títulos; lo que no se hace es regalarle el dinero que le falta para llenar la
  liga. Un club desaparecido ya no asciende, no desciende y no se inscribe en la
  temporada siguiente.
- `backend/app/application/club_evolution_service.py`, llamado desde
  `season_service.process_season_boundaries` **antes** de mover clubes: las
  cuentas se cierran primero, porque un club que cierra no asciende.
- Dos tablas nuevas: `club_season_ledgers` —con clave única `(club_id, season)`,
  que es lo que hace **idempotente** la liquidación si se reintenta un avance— y
  `club_organization_changes`, que guarda cada cambio con su causa y no
  sobrescribe el pasado.
- `simulation/generation/season_forecast.py`: **vuelve a presupuestar** la
  temporada siguiente con la misma `estimate_club_finances()` de la generación,
  con la base social y el alcance ya evolucionados y con los recursos de la zona
  repartidos entre los clubes que siguen vivos. La bolsa publicitaria local no
  crece porque un club crezca: lo que uno gana lo pierden sus vecinos, y lo que
  deja un club que desaparece se reparte. Sin esto, la evolución sería
  decorativa.
- Ficha de club con el libro mayor temporada a temporada (real frente a
  previsto, asiento por asiento) y su historia institucional.
- 9 pruebas en `simulation/tests/test_season_close.py` y 7 en
  `backend/tests/test_club_evolution.py` (P5-01 a P5-07).

**Lo que P5 no resuelve, y se sabe:**

- Las **tasas de cobro** (80–99 % en cuotas, 55–100 % en patrocinio, 8 % de
  incumplimiento) son heurísticas declaradas, no datos observados. Lo que está
  garantizado es que cobrar no es presupuestar, no el decimal exacto.
- **No hay fusiones ni refundaciones.** V2 §6.3 las menciona; aquí un club
  crece, se encoge o desaparece, pero dos clubes no se unen todavía.
- **No hay mercado de fichajes** y, por tanto, el gasto en plantilla no
  responde a lo que un club puede pagar por un jugador concreto. Eso es Etapa 4.
- La **escala profesional** sigue por debajo de la realidad: sin derechos de
  televisión ni traspasos, un club profesional de este simulador recauda como
  un club semiprofesional grande.

## Estado por etapas

| Etapa | Alcance | Estado |
|---|---|---|
| 0 | Monorepo, FastAPI, SvelteKit, Postgres/SQLite, Alembic, tests, Docker | **Hecho** |
| 1 | Vertical: universo → liga independiente → generación → calendario → partidos → tabla → avanzar → persistir | **Hecho** |
| 2 | Motor declarativo de relaciones, ascenso/descenso transaccional, grupos/divisiones | **Hecha** (movilidad, divisiones, siembra por grupo, cuadro dibujado con sus rondas y sus cruces); falta el repechaje interregional |
| 3 | Internacional: franquicias por ciudad, selecciones, elegibilidad por liga doméstica | No empezado |
| 4 | Personas e IA: desarrollo por edad, scouts falibles, ledger, patrocinios, fichajes | Scouts falibles y **ledger de temporada** hechos; faltan desarrollo por edad, patrocinios como entidad y fichajes |
| 5 | Béisbol detallado lanzamiento por lanzamiento, clima, parque 2D, replay | No empezado |
| 6 | Escala, snapshots, historia, exportación | No empezado |

## Etapa 0 — hecho cuando

- [x] `simulation` importable y testeable sin servidor ni base de datos.
- [x] FastAPI con `/health` y configuración por entorno.
- [x] SvelteKit tipado que consume la API real.
- [x] Alembic con migración inicial que corre en SQLite y en PostgreSQL.
- [x] `docker compose` con volumen persistente para Postgres.
- [x] `make test`, `make lint` verdes.

## Etapa 1 — hecho cuando

> Un usuario crea «Liga Municipal de Ciudad Juárez» de 12 clubes y simula una
> temporada completa sin editar un solo club.

- [x] Crear/cargar universo con semilla y fecha inicial.
- [x] Crear liga **independiente** municipal o nacional desde el wizard.
- [x] Perfiles geográficos desde fixture local con procedencia marcada.
- [x] Generación seeded de clubes, marca, estadios, plantillas y personas.
- [x] Calendario válido con balance de localías y días de descanso.
- [x] Motor de partidos por turno de bateo con box score consistente.
- [x] Clasificación, calendario, plantillas y fichas vía API y UI.
- [x] `advance` idempotente, persistente y con lock por universo.
- [x] Playoffs al cierre de la temporada regular.

## Etapa 2 — qué hay y qué falta

> **Hecho cuando:** dos divisiones vinculadas intercambian exactamente N clubes y
> otra liga independiente permanece intacta. → **cumplido**, con prueba:
> `backend/tests/test_mobility.py`.

Implementado:

- [x] `MobilityConfig` tipado y versionado en la fila de la relación, con la
      cuota total como autoridad única y reparto por rama.
- [x] Plan de intercambio en el motor puro (`simulation/competitions/mobility.py`):
      criterios de ascenso y descenso, campeón de postemporada, requisitos de
      ascenso (aforo, deuda) con políticas `substitute`, `block` y `exception`,
      balance obligatorio y reparto territorial de descensos.
- [x] Aplicación transaccional: se cierran y abren `club_memberships` sin tocar
      `club.id`, estadio, plantilla, caja, deuda ni historia.
- [x] Idempotencia por `season_transitions(upper_competition_id, season)`.
- [x] Frontera de temporada dentro del avance del día: espera a que toda la
      escalera cierre y abre la temporada siguiente con los clubes existentes.
- [x] Reescalado de presupuesto y reputación al cambiar de categoría, con
      procedencia y declarado como heurística.
- [x] Vínculos filiales/juveniles que **no** mueven clubes, con schema propio.
- [x] `PATCH`/`DELETE` de relaciones: la cuota se edita una vez y la ven las dos
      ligas; desvincular devuelve la independencia sin reescribir el pasado.
- [x] API: `GET /competitions/{id}/mobility`, `GET /editions/{id}/mobility-projection`,
      `GET /universes/{id}/mobility-history`.
- [x] Interfaz: paso B del asistente con la naturaleza exacta del vínculo
      (división, filial, juvenil, desarrollo), sus plazas y sus requisitos;
      grafo con la regla efectiva editable y el historial de movimientos; zona
      de ascenso y descenso en la clasificación; categorías anteriores y
      movimientos en la ficha del club.
- [x] Una competición no puede nacer dependiente: la dependencia la crea la
      relación, y el reglamento que la declare se rechaza con una explicación.
- [x] Casos de la especificación C04, C05, C06, C07 cubiertos con temporadas
      simuladas de verdad, no con validaciones.

- [x] **Grupos, divisiones y conferencias** dentro de una misma competición:
      bloque `structure` del reglamento, reparto geográfico o por recursos con
      su motivo registrado, calendario asimétrico (más vueltas dentro del grupo
      que fuera) con localías repartidas por orientación euleriana, tabla con
      puesto de división y siembra de playoffs por campeones de grupo más
      repechajes. El reparto se rehace cada temporada, así que un club
      ascendido entra en la división que le toca por geografía. Ver
      `docs/adr/0008-divisiones-dentro-de-una-competicion.md`.

- [x] **Playoffs con pase directo y plazas que no sean potencia de dos.** Seis
      clasificados —dos campeones de división y dos repechajes— caben en un
      cuadro de ocho donde las dos mejores siembras esperan en la segunda
      ronda. `PlayoffRules` deriva `bracket_size`, `byes` y `rounds`;
      `seed_bracket` devuelve la primera ronda **y** los que esperan;
      `next_round` los incorpora resembrando con todos. Los pases directos se
      guardan en `competition_editions.playoff_byes` porque la ronda siguiente
      se construye otro día y en otra transacción.
- [x] **El asistente dibuja lo que producen sus números.** `POST
      /schedule/preview` calcula con el mismo motor el calendario, los cruces y
      el cuadro de unos parámetros cualesquiera, sin universo y sin escribir
      nada; el paso 6 lo pinta mientras el usuario mueve los controles: resumen
      de partidos y días, barra por club con su reparto dentro y fuera de la
      división, matriz de cruces con colores por tipo de enfrentamiento, las dos
      primeras semanas día a día y el cuadro de postemporada con el motivo de
      cada clasificado y la ronda en la que entra.

- [x] **Estructura por fases con divisiones asimétricas y editor gráfico.** Una
      competición es una secuencia de fases; una fase de tabla tiene divisiones
      que **no tienen por qué parecerse** —otras plazas, otras vueltas, otros
      clasificados— y las **puertas** (`Gate`) dicen qué puestos pasan y por qué
      ruta. El paso 6 del asistente es un editor donde las plazas se arrastran
      entre divisiones. Ver
      `docs/adr/0010-estructura-por-fases-y-editor-grafico.md`.

- [x] **El cuadro se dibuja: tablero de postemporada y cruces declarados.** La
      pestaña de postemporada es un kanban: la primera columna es la
      competición entera y las demás son las rondas que el usuario añade y
      nombra. Una plaza clasifica porque está puesta en una ronda, así que las
      etiquetas de pase directo y repechaje desaparecen —`GateRoute.SEED` es una
      entrada neutra cuyo significado lo dan su procedencia y su destino—. Con
      `playoffs.seeding = "staged"` las rondas son las dibujadas y no las que
      deduciría la potencia de dos, y `round_pairings` decide por ronda si se
      resiembra por la tabla, se sortea o el cuadro no se mueve
      (`fixed`, el cuadro de copa). Eso cubre tanto una copa antigua como una
      postemporada de la MLB, donde los campeones de división esperan la segunda
      ronda. Ver
      `docs/adr/0011-cuadro-dibujado-y-tablero-de-postemporada.md`.

Falta para cerrar la etapa:

- [ ] **Una segunda fase de tabla** (liguilla entre los clasificados antes de
      los cruces). Cabe en el modelo y el reglamento la rechaza con un mensaje
      explícito en vez de aceptarla sin jugarla: hace falta una clasificación
      **por fase**, no por edición.
- [ ] Promoción por repechaje interregional entre ramas (hoy el reparto de
      plazas es por cuota y territorio, sin eliminatoria entre alimentadoras).

## Contrato de WebSocket previsto (no implementado)

Mensajes versionados: `tick_started`, `tick_completed`, `game_completed`,
`league_updated`, `job_progress`, `job_failed`, cada uno con `v`, `job_id` y
`universe_id`. Perder la conexión no cancela nada: el cliente recupera estado
por `GET /sim/status`. Hoy la UI hace polling de ese endpoint.

## Nota de evolución de esquema

`RULESET_SCHEMA_VERSION` pasó a `1.1.0` al añadir `season.offseason_days`. Un
reglamento guardado con `1.0.0` sigue validando —el campo tiene valor por
omisión— pero su `checksum` recalculado ya no coincide con el almacenado,
porque el volcado canónico incluye ahora el campo nuevo. Afecta solo a bases
creadas antes de esta migración; las ediciones ya jugadas no se reescriben.

## Anexo de personas y organigramas — hitos H0–H7

Origen: `Baseball_Universe_Personas_Organigramas_v1_1.md` (v1.1). Define el
motor humano que la génesis institucional y la Fase 2 necesitan: una plantilla
de 52 atributos compartida por toda persona del universo, relaciones como
aristas dirigidas y organigramas con unidades anidadas y asignaciones N:M.

El propio anexo (§17.3, §20, §24) ordena **no relegar la deuda del FIX V2**, y
por eso la corrección de aforos, mercados y divisor de caja del 25/10/2026 fue
antes que H0. Lo que queda de esa deuda está anotado en
`docs/simulation-calibration.md`.

| Hito | Alcance | Estado |
|---|---|---|
| H0 | Auditoría, mapa de clases, riesgos y ADR | **Hecho** — `docs/personas-h0-auditoria.md`, ADR 0012 |
| H1 | Catálogo de los 52 atributos, validación y generación con factores latentes | **Hecho** — `simulation/persons/` |
| H2 | Personas del universo: persistencia versionada, materialización y backfill | **Hecho** — `person_universal_profiles`, `person_service` |
| H2 bis | La generación de competiciones pide personas al universo | **Retirado** — ADR 0013: ya no se generan plantillas, así que no hay a quién pedir |
| H3 | Generación con factores latentes y semillas por subdominio | Pendiente |
| H4 | Organigramas, cargos con titular y génesis antes del reparto de plantillas | **Fundación hecha** — ADR 0014: raíz, Gerencia y propietarios o representantes como personas reales. El crecimiento del organigrama (crear, fusionar y cerrar departamentos) queda pendiente |
| H5 | Relaciones, estados y envejecimiento | Pendiente |
| H6 | Creencias por observador y política de decisión | Pendiente |
| H7 | Vistas de organigrama, histórico y benchmark | Pendiente |

Cuatro defectos medidos que estos hitos corrigen, y que la auditoría documenta
con fichero y línea:

1. **Toda persona es un jugador.** `PersonRole.PLAYER` es el único valor que el
   generador produce; mánagers, tesoreros y scouts son cadenas de texto sin
   titular.
2. **De los seis números psicológicos, solo `composure` se lee** en toda la base
   de código, y los seis se sortean independientes entre sí.
3. **Las personas pertenecen a la edición que las creó**, así que dos ligas en
   la misma ciudad generan poblaciones disjuntas.
4. **Nadie envejece ni aprende:** `people.state` se escribe una vez y no vuelve
   a tocarse.

Lo que H1 y H2 dejaron hecho, y lo que deliberadamente no tocaron:

- **Existe la persona del universo.** `person_service.materialize_person` crea a
  alguien que vive en un territorio, con sus 52 atributos en la misma
  transacción, **sin** posición de juego, valoración global ni papel. Las
  columnas deportivas de `people` pasaron a admitir nulo: antes era imposible
  guardar a un tesorero.
- **La identidad ya no la pone una competición.** La clave de una persona del
  territorio es `p:<lugar>:<cohorte>:<serial>`, y `available_people` es la
  consulta que hay que hacer antes de materializar a nadie.
- **Los jugadores que ya existen reciben su perfil al pedirlo**
  (`ensure_profile`), conservando los seis números que el universo ya conocía.
  `composure` llega intacto a `inhibitory_control`, que es lo que mantiene
  reproducibles los partidos ya jugados.
- **La generación de plantillas se retiró por completo** (ADR 0013). No hay
  jugadores, no hay draft y no hay agentes libres: un club nace con su
  identidad, su gobierno, su sede y sus cuentas, y sin una sola persona dentro.
  La única puerta por la que entra gente al universo es
  `person_service.materialize_person`.
- **Los partidos están desactivados y se dice.** Avanzar el reloj falla con
  `ROSTERS_MISSING` nombrando a los clubes sin plantilla. Crear universos,
  elegir territorio, generar clubes, inscribirlos y calendarizar sigue
  funcionando; jugar, no.
- **36 pruebas en `xfail(strict=True)`** con su causa. Pasarán el día en que
  exista la mecánica de selección, y una `xfail` estricta que pasa falla la
  batería: es la lista de lo que hay que devolver a la vida.

## Identidad generativa (ADR 0015)

Nombre y logo dejaron de salir de listas terminadas. El motor nominal construye
varias candidatas con morfemas y gramáticas del idioma declarado, puntúa
naturalidad, rechaza similitudes y conserva la **familia** del concepto elegido.
El perfil institucional persistente —semilla, versión, referencias y decisiones
creativas separadas— alimenta tanto ese nombre como un árbol gráfico con treinta
motivos paramétricos. De él salen las variantes principal, secundaria, monograma,
reducida, gorra y fondos claro/oscuro.

Tres defectos medidos que esto corrige:

1. **El 59 % de los escudos no se leía** (contraste mediano 2,2:1, mínimo
   1,0:1). La paleta se genera ahora en OKLCH y el contraste se **exige**: 0 de
   600 por debajo del umbral de WCAG.
2. **El símbolo no sabía nada del nombre**: un club llamado Nopaleras llevaba un
   elefante tan a menudo como un cactus, que ni existía.
3. **El contrato no se validaba** y su único intérprete era un componente del
   frontend: un motivo mal escrito salía como estrella y nada podía exportar un
   escudo sin un navegador. Ahora el motor lo dibuja y lo sirve en
   `/clubs/{id}/crest.svg`.

## Nombres acuñados (ADR 0016)

El motor nominal ya no combina nombres acabados: combina **morfemas**. Medido
sobre 96 clubes de una misma región, antes «Viento» salía siete veces y las
marcas sólo se distinguían por el prefijo, porque el inventario eran 24 palabras
por idioma y el control de duplicados comparaba la cadena final.

Lo que hay ahora:

- **673 raíces** —165 en español— con el alomorfo que cada una admite por clase
  de sufijo, y las reglas ortográficas del idioma para aplicarlo: `barranca` +
  `-ero` da «barranquero», `médano` + `-ero` da «medanero». Español e inglés
  derivan; ocho idiomas más tienen inventario curado que se usa tal cual.
- **Un filtro fonotáctico** por palabra acuñada: silabación de ataque máximo,
  ataques y codas del idioma, sílaba repetida y longitud.
- **Tres vetas de identidad**, una por club: territorio (altitud, franja
  climática, tamaño de plaza), época (año de fundación) y patronazgo (la casa o
  la empresa que lo sostiene). La veta restringe vocabulario y gramática, y
  degrada en vez de fallar cuando falta el dato.
- **La presión del universo es sobre la raíz y la plantilla**, no sobre la
  cadena: 24 clubes de una misma plaza salen con 24 raíces distintas.
- **El nombre guarda de dónde salió**: veta, hecho que lo motivó y acuñación
  («mezquite + -al») viajan en el perfil de identidad del club.

Coste: 5,7 ms por club. El año de fundación pasó a su propio cauce RNG porque la
veta de época lo necesita antes del nombre; el sorteo histórico se sigue
consumiendo, así que las cuentas no se mueven.

## Escudos blasonados (ADR 0017)

El escudo dejó de salir de una plantilla. Antes había **una** silueta escrita a
mano y **cinco** composiciones fijas, con una figura sola en el centro: cien
escudos se repartían en cinco grupos reconocibles. Ahora:

- La **silueta se construye** por familias de blasón —inglés, francés, ibérico,
  italiano, de torneo, barroco, estandarte, ojival—, con parámetros continuos:
  500 semillas dan 500 contornos distintos.
- El **emblema tiene capas**: 13 particiones del campo, 10 piezas honorables, el
  mueble principal, 7 muebles menores geométricos —o un segundo símbolo de la
  misma familia—, escudete cuando el fondo lo pide, y exteriores construidos
  (cinta, corona, estrellas, año de fundación).
- La **colocación se calcula**: `width_at` dice cuánto escudo hay a cada altura,
  y ningún mueble menor se pone a menos de la distancia a la que deja de tocar
  al principal.
- Un **solo color fuerte** por escudo, con el contraste medido contra el campo y
  contra la figura.
- Los símbolos más repetidos —torre, yunque, engranaje, abstracto— tienen
  anatomía variable, no un único parámetro.

Medido sobre las cien identidades de la galería de aceptación: **100 de 100 con
estructura gráfica distinta**, donde el criterio pedía 50.

## Símbolos y arquetipos de marca (ADR 0018)

El escudo ya no se repetía, pero su contenido sí: quince de los veintidós
símbolos eran el mismo dibujo con un número movido, ocho motivos del mapa
semántico no tenían contorno y todo era «escudo con una figura».

- **30 símbolos con anatomía propia**, y los treinta dan 24 dibujos distintos de
  24 semillas. El rayo son sus siete vértices; la llama, de una a tres lenguas;
  el cactus tiene dos especies; el puente puede ser colgante.
- **`DRAWABLE_FALLBACK` vacío**: lo que el nombre promete, el escudo lo dibuja.
- **El lienzo manda en un solo sitio**: `generate_symbol` mide y encaja cada
  figura, así que ninguna se sale y «escala 0,6» significa lo mismo para todas.
- **Tres arquetipos de escudo** —simple, cuartelado con una figura por cuartel,
  y acompañado con tenantes, cimera y compartimento— y **cinco de marca**
  —escudo, disco, libre, parche y banderín—, porque en la realidad no todo es un
  escudo.

Medido sobre 200 escudos: 200 estructuras gráficas distintas.

## De todo tipo, y sin repetirse (ADR 0019)

Quedaban dos problemas de reparto. El primero: **88 de cada 100 marcas eran
escudos heráldicos**, porque esa dirección pesaba 16,0 contra 0,15 de las
rotuladas. El segundo: esas cinco direcciones rotuladas eran cinco recetas con
las cajas escritas a mano.

- La **marca rotulada es ahora un sistema**: cinco marcos (ninguno, roundel,
  escudo, cápsula, banderín), cuatro modos de monograma —incluido el grande y
  velado al fondo—, rótulo recto o en arco, seis adornos y cuatro pies.
- **Regla de tinta**: dentro de un marco la letra va clara; fuera, del color del
  club con perfil. Rotular en `field` sobre un marco de `field` dejaba la marca
  invisible.
- **Reparto deliberado de direcciones**: 34 heráldicas, 18 simbólicas y 48
  rotuladas de cada 100, inclinado por la personalidad del club. El criterio de
  aceptación se cambió a propósito: antes exigía 65 % de heráldicas, es decir,
  exigía la falta de variedad.
- **Dos arquetipos más**: escudo con las **iniciales dentro** —lo más
  característico de un escudo de fútbol— y marca con **empuje diagonal**.
- **El halcón y el toro miran de lado**: vista de perfil además de la frontal.

Medido: 1.000 escudos del mismo club dan 1.000 estructuras distintas, y 1.000
clubes distintos reciben 1.000 marcas distintas, ninguna repetida.

## Fechas de temporada y cuadro editable a la vista (ADR 0020 y 0021)

Dos quejas del mismo paso del asistente.

**Las fechas.** Toda liga arrancaba el día en que se creaba. Ahora el
reglamento declara `season.start_date` —sólo el arranque; el final lo pone el
calendario que el motor construye— y `SeasonRules.opening()` lo resuelve en un
solo sitio: la fecha tal cual en la primera edición, su aniversario en las
siguientes, nunca antes del día del mundo y nunca antes de la pausa entre
temporadas. Las competiciones que intercambian plazas abren su temporada **el
mismo día**, el más tardío de la escalera, porque el intercambio siguiente no
se resuelve hasta que todas hayan terminado. La previsualización devuelve el
calendario día a día con sus cruces, y el asistente lo dibuja mes a mes.

**El cuadro.** Las salidas de cada llave —ganador y perdedor— salen del pliegue
y se ven siempre, con un menú «⋯» que conecta de un clic, incluido el destino
«cruce nuevo» que es el que crea el partido por el tercer puesto. Para que eso
no fuera una promesa vacía, el motor aprendió qué es una **llave de
consolación** —aquella a la que solo se llega perdiendo—: su ganador es una
salida final legítima que no disputa el título, así que un cuadro con tercer
puesto deja de ser «dos campeones» y pasa a validar. Se pueden
abrir varias llaves a la vez. Y vuelven a la vista los mandos que una hoja de
estilo había escondido: formato de la postemporada, estado del camino, recuento
de cada ronda y el botón de quitarla.

## La paleta del club: dos, tres y tres (ADR 0022)

El compositor de marcas tenía la paleta escrita a mano: el tono del campo se
sorteaba **entre cinco** y la marca, la tinta y el papel eran constantes. Tres
de cada cuatro colores de una identidad no eran de esa identidad.

Ahora cada club tiene ocho colores con oficio —dos principales, tres
secundarios y tres terciarios, incluido un metal con nombre— derivados de un
esquema de armonía declarado (monocroma, análoga, complementaria, complementaria
dividida o tríada) que la personalidad institucional inclina. Se imponen dos
cosas: el **contraste WCAG** de lo que acaba pegado y la **distinción
perceptual** en OKLab, que es otra cosa —dos tonos opuestos con la misma
claridad tienen contraste 1:1—. La paleta se compone una vez por club, se
guarda en su perfil, la enseña su ficha con el oficio de cada color, y el
blasón dibuja con ella: las tinturas de las particiones, el color de los
muebles y el filete de metal de la bordura.

Medido sobre 200 clubes: 200 bases distintas y 200 colores principales
distintos.

## Orden recomendado para la siguiente iteración

1. Rasterizado del escudo a PNG —favicon por club e imagen para compartir— y
   variantes adicionales horizontal/monocroma. Las siete variantes SVG de uso
   inmediato ya se generan, persisten y exploran en la ficha del club.
2. Que el organigrama **crezca**: crear un departamento cuando aparece el
   trabajo que lo justifica, fusionarlo en una crisis, cerrarlo, y emitir los
   eventos institucionales de cada cambio.
3. La mecánica de selección: cómo una persona del universo pasa a jugar en un
   club. Es la que devuelve a la vida las 36 pruebas en `xfail`.
3. `QualificationPath` ejecutándose (casos C08 y C12): extracción de cupos a
   copas sin crear jerarquía, con regla de reasignación si dos vías clasifican
   al mismo club.
3. Mover el avance a un proceso worker con cola en Postgres y añadir WebSocket.
4. Liga internacional de clubes con franquicias por ciudad (C11) y selecciones
   nacionales con elegibilidad por liga doméstica (C09, C10).
