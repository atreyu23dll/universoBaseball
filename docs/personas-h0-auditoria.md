# H0 — Auditoría del Motor Universal de Personas y de los organigramas

- **Fecha:** 25 de octubre de 2026
- **Origen:** `Baseball_Universe_Personas_Organigramas_v1_1.md` (anexo técnico,
  v1.1), entregable **H0** de su §20: «mapa de clases actuales, ADR y riesgos;
  sin código destructivo».
- **Decisiones que de aquí salen:** ADR 0012.
- **Estado:** auditoría cerrada. **No hay código nuevo en este hito**, a
  propósito: H0 existe para no empezar a escribir tablas antes de saber qué
  rompemos.

Este documento responde tres preguntas y nada más: qué hay hoy, en qué se
diferencia de lo que el anexo exige, y qué puede salir mal al cerrar esa
distancia.

---

## 1. Mapa de lo que existe hoy

| Concepto del anexo | Qué hay en el repositorio | Dónde | Veredicto |
|---|---|---|---|
| `Person` con identidad persistente | `Person` (dataclass) y tabla `people` con `person_key` único por universo | [model.py:124](../simulation/people/model.py#L124), [models.py:580](../backend/app/infrastructure/models.py#L580) | **Existe**, pero la identidad es de la edición (ver H4) |
| `UniversalHumanProfile` (52 atributos) | `Cognition` con **6** atributos, solo en quien juega | [model.py:89](../simulation/people/model.py#L89) | **No existe** |
| `PsychologicalProfile` / `CognitiveProfile` / `SocialProfile` | — | — | **No existe** |
| `RelationshipEdge` (grafo dirigido, 8 campos) | — | — | **No existe** |
| `DomainCompetencies` | `BattingAttributes`, `PitchingAttributes`, `FieldingAttributes`, `PhysicalAttributes`, `Development` | [model.py:55-110](../simulation/people/model.py#L55) | **Existe** y ya está separado del núcleo: es el `BaseballSkillProfile` del anexo §13 con otro nombre |
| `RoleAssignment` persona ↔ unidad ↔ función | `RoleAssignment` (dataclass) **sin persona**, serializado en `clubs.organization` | [organization.py:108](../simulation/generation/organization.py#L108), [clubs.py:437](../simulation/generation/clubs.py#L437) | **Existe el concepto, no el vínculo** (ver H6) |
| `GovernanceModel` | `GovernanceModel`, 9 valores, con `has_single_owner` y `receives_institutional_support` | [model.py:41](../simulation/economy/model.py#L41) | **Existe y es reutilizable tal cual** (§23.7 paso 2 lo conserva) |
| `OwnershipInterest` | Solo `has_owner`, derivado del gobierno | [organization.py:139](../simulation/generation/organization.py#L139) | **No existe**, y el anexo lo declara opcional |
| `OrganizationUnit` / `OrganizationPosition` | — | — | **No existe** |
| `AuthorityGrant` / `TimeBudget` / `Workload` | — | — | **No existe** |
| `InstitutionalMembership` | `RosterAssignment` (persona ↔ club, con intervalo) y `ClubMembership` (club ↔ competición) | [models.py:616](../backend/app/infrastructure/models.py#L616) | **Existe para jugadores**; es el patrón a imitar para los cargos |
| `BeliefObservation` / `ScoutingReport` | Un escalar por persona: `development.scouted_potential` + `scouting_error` | [people.py:284](../simulation/generation/people.py#L284) | **Embrión**, sin observador (ver H7) |
| Población latente por cohortes | Solo rangos de edad dentro de la generación de un pool | [people.py:156-205](../simulation/generation/people.py#L156) | **No existe** |
| Eventos institucionales (`ROLE_ASSIGNED`, `ORG_UNIT_*`…) | 17 tipos de evento, de los cuales `CLUB_ORGANIZATION_CHANGED` es el único del ámbito institucional | [events.py:11](../simulation/core/events.py#L11) | **Parcial** |

Tablas en la base hoy: 35. Ninguna de las siete que el anexo pide
(`person_universal_profiles`, `person_profile_checkpoints`,
`person_profile_events`, `relationship_edges`, `organization_units`,
`organization_positions`, `organization_role_assignments`).

---

## 2. Siete hallazgos, medidos

### H1 — Una persona es siempre un jugador

`PersonRole` declara siete valores —jugador, mánager, entrenador de pitcheo,
bateo, scout, gerente, presidente— y el generador **solo produce uno**:
`role=PersonRole.PLAYER` en [people.py:299](../simulation/generation/people.py#L299)
es la única asignación de todo el repositorio. No hay una sola persona en ningún
universo que no juegue al béisbol.

Consecuencia directa: los mánagers, tesoreros, organizadores y responsables de
salvaguarda de los que habla la ficha de un club **no son nadie**. Son cadenas
de texto.

### H2 — De los seis números psicológicos, uno afecta a la simulación

`Cognition` guarda `composure`, `competitiveness`, `work_ethic`,
`risk_tolerance`, `sociability` y `learning`. El único que se lee en algún sitio
es `composure`, y solo para construir los perfiles de bateador y lanzador del
motor de partidos ([rates.py:118](../simulation/baseball/rates.py#L118) y
[rates.py:144](../simulation/baseball/rates.py#L144)).

Los otros cinco se generan, se validan, se guardan en `people.attributes` y
**nadie los consulta jamás**. Esto es una buena noticia para la migración: el
único número cuyo valor hay que preservar bit a bit para que los partidos ya
jugados sigan dando el mismo resultado es `composure`.

### H3 — Los seis se generan independientes entre sí

[people.py:274-282](../simulation/generation/people.py#L274) sortea los seis con
una normal truncada cada uno, sin estructura de covarianza. Es el antipatrón que
el anexo §9.1 prohíbe —«52 valores independientes»— a escala de seis. Cuando se
pase a 52 hay que introducir factores latentes, o el problema se multiplica por
nueve.

### H4 — Las personas son de la edición, no del universo

La clave de una persona es
`f"{edition_key}:{market.place_key}:{i}"` ([people.py:413](../simulation/generation/people.py#L413)),
su semilla se deriva del `edition_key`, y al confirmar una competición se
insertan filas nuevas sin consultar si esa gente ya existe
([competition_service.py:1059-1084](../backend/app/application/competition_service.py#L1059)).

Dos ligas en la misma ciudad producen **dos poblaciones disjuntas**: nadie puede
jugar en las dos, nadie compite por nadie, y la misma persona de la misma
colonia se duplica. Incumple el §8.1 («antes buscar y evaluar individuos ya
existentes»), el §12.1 («el mercado de talento existe antes de fundar cada
club») y la prueba P2-13 del propio anexo.

Es el hallazgo más caro de corregir y el que más cambia de sitio: afecta a la
identidad, al determinismo y a la Fase 2 entera.

> **Corregido el 25/10/2026.** La clave de una persona es ahora territorial
> (`p:<plaza>:<serial>`), su semilla se deriva de ella y la generación de una
> competición recibe a la gente disponible del territorio antes de materializar
> a nadie. Medido en un universo nuevo: la primera liga de Ciudad Juárez crea
> 220 personas y deja 44 libres; la segunda crea 106 en vez de 150 y alinea a 25
> jugadores que ya vivían allí. Las personas anteriores conservan su clave con
> identificador de edición, como dice el ADR 0012 D4.

### H5 — Nadie envejece, nadie aprende, nadie se cansa entre partidos

`people.state` se escribe una vez, con valores fijos, al crear la competición
([competition_service.py:1079](../backend/app/application/competition_service.py#L1079)):
`{"fatigue": 0.0, "morale": 0.6, "form": 0.0, "days_until_available": 0}`. No
vuelve a tocarse nunca. La fatiga que el motor de partidos usa se calcula dentro
del partido y se descarta al terminar.

El cierre de temporada hace evolucionar al **club** —caja, deuda, afición,
alcance, sede, gobierno— y no toca a las personas: `season_service` dice
explícitamente que no genera ni modifica personas. Un universo de treinta
temporadas tiene jugadores de la misma edad y la misma habilidad que el primer
día.

### H6 — Los cargos no tienen persona, ni autoridad, ni carga

`assign_roles` ([organization.py:233](../simulation/generation/organization.py#L233))
decide qué funciones necesita un club y si puede pagarlas, con una lógica que ya
es razonable: reparte un presupuesto de meses de personal, marca puestos como
`paid`, deja otros `vacant` y acumula funciones en la misma figura mediante
`doubles_with`.

Lo que falta es **todo lo que las convierte en responsabilidades de alguien**:

- `doubles_with` apunta al **nombre de otro cargo**, no a una persona. «La misma
  persona que organizador» es una frase, no un identificador.
- No hay autoridad: nada dice quién puede inscribir al club o firmar un pago.
- No hay carga horaria ni acumulación entre clubes.
- No hay unidades: la estructura es una lista plana de seis a ocho funciones,
  idéntica en forma para un club llanero y para una franquicia.
- Todo vive en una columna JSON del club (`clubs.organization`), que además es
  **contrato de la API y de la interfaz**: la ficha de club renderiza
  `club.organization.roles` ([+page.svelte:160](../frontend/src/routes/clubes/%5Bid%5D/+page.svelte#L160))
  y el preview lo expone ([competition_service.py:424](../backend/app/application/competition_service.py#L424)).

### H7 — Hay un embrión de información imperfecta, y conviene no romperlo

El reparto de plantillas es un draft con información imperfecta: los clubes
eligen por `observed_overall` y no por la habilidad real, y la **ventana de
decisión depende de sus recursos** —un club con scouting pagado mira menos
nombres y acierta más
([clubs.py:671](../simulation/generation/clubs.py#L671))—. Eso es, en pequeño, lo
que el anexo §11.6 pide.

Pero el error no es de nadie: `scouting_error` es un escalar sorteado **una vez
por persona** ([people.py:284](../simulation/generation/people.py#L284)), mayor
cuanto más joven es. Todos los observadores del universo comparten exactamente
la misma creencia equivocada. No hay observador, ni fecha, ni fuente, así que
dos scouts no pueden discrepar (§14.3).

---

## 3. Riesgos

| | Riesgo | Mitigación que el ADR 0012 adopta |
|---|---|---|
| R1 | **Volumen.** 52 flotantes por persona, con estados que cambian a diario, multiplicados por miles de personas y treinta temporadas. | JSONB validado + actualización perezosa + checkpoints solo en hitos. Prohibido escribir los 52 por persona y por día (§18.5 P4-38). Benchmark antes de ampliar. |
| R2 | **Determinismo.** Pasar de personas por edición a personas por universo cambia claves y semillas; `test_c03_determinismo` y los fixtures guardados dependen de ellas. | Las personas existentes **conservan su clave**. El esquema nuevo se aplica a quien se materialice a partir de ahí, con semilla derivada de la identidad (`universe + person_id + schema_version`), no del orden de iteración ni de la edición. |
| R3 | **Resultados de partidos ya jugados.** Si `composure` cambia de valor al re-enraizarlo en el perfil universal, los partidos simulados dejan de ser reproducibles. | `composure` se migra por identidad, no se vuelve a sortear, y `Cognition` sobrevive como **vista derivada** de los 52 para que `simulation/baseball` no se entere. Prueba de regresión con semilla fija sobre un partido completo. |
| R4 | **Contrato de interfaz.** `clubs.organization.roles` lo consume la ficha de club y el preview. | Las tablas nuevas son la fuente de verdad; el JSON se mantiene como **proyección derivada** mientras el frontend no se mueva. |
| R5 | **Divergencia del catálogo.** Los 52 nombres tienen que coincidir en Python, en el JSON Schema, en el DTO y en TypeScript (§18.1-7). | Un único registro en Python; el tipo de TypeScript se genera de él, no se escribe a mano. |
| R6 | **Alcance.** El anexo son siete hitos y el repositorio todavía arrastra deuda de calibración económica (la escala de afición y asistencia, anotada el 25/10/2026). | H1 es solo catálogo y validación, sin comportamiento. Ningún hito del anexo cierra deuda del FIX V2, y ninguno la tapa. |
| R7 | **Menores.** Hoy `involves_minors` solo añade un cargo `responsable_de_salvaguarda` sin titular. Con personas reales pasa a ser una regla de autorización. | §23.5: la responsabilidad sobre menores exige titular válido y no se cubre con una persona inventada; si no hay candidato, se advierte y se bloquea. |
| R8 | **Fuga de conocimiento entre clubes.** Una persona con cargos en dos instituciones podría arrastrar creencias de una a otra. | El contexto de decisión es por asignación, no por persona (§23.5). Se diseña en H6; hasta entonces no hay motor de decisiones que pueda filtrar nada. |

---

## 4. Plan de migración, mapeado a este repositorio

Los hitos son los del anexo §20; lo que añade esta columna es **qué fichero se
toca y qué prueba lo cierra**.

| Hito | Qué se hace aquí | Cierra cuando |
|---|---|---|
| **H0** | Este documento y el ADR 0012. | *Hecho.* |
| **H1** | `simulation/persons/`: catálogo de los 52 con sus clases y rangos, perfil validado con Pydantic, y generación con **seis factores latentes** (se adelantó lo que el plan original dejaba para H3, porque sortear 52 números independientes para tirarlos después no tenía sentido). | *Hecho.* P0-01…07 y P1-08…13 en `simulation/tests/test_persons_universal.py`. |
| **H2** | `person_universal_profiles` y `person_service`: materializar a una persona del territorio con su perfil, buscar a quien ya existe antes de crear a nadie, y dar perfil a los jugadores anteriores conservando los seis números conocidos. Siete columnas de `people` pasan a admitir nulo. | *Hecho.* `backend/tests/test_persons_universe.py`. Quedan fuera `person_profile_checkpoints`, `person_profile_events` y `relationship_edges`: son esquema sin usuario hasta H5. |
| **H2 bis** | Que `generate_talent_pool` **pida** personas al universo en vez de inventarlas por edición. | *Retirado el 25/10/2026* (ADR 0013): no se generan plantillas, así que no hay a quién pedir. El hallazgo H1 —toda persona es un jugador— queda resuelto por la vía contraria: ninguna lo es. |
| **H3** | Curvas de desarrollo y recalibración de los parámetros de generación con datos de uso. | P1-11 con bandas medidas, no solo plausibles. |
| **H4** | `OrganizationUnit`, `OrganizationPosition`, `organization_role_assignments`. `assign_roles` pasa a producir asignaciones **con `person_id`**, y las personas responsables se materializan o se reutilizan del territorio **antes** del reparto de plantillas. `clubs.organization.roles` queda como proyección. | G01…G08 y P3-24/25: club llanero sin propietario, raíz técnica única, una persona con tres cargos sin duplicar su ficha. |
| **H5** | Aristas de relación creadas por interacciones reales, estados que se mueven con el reloj y envejecimiento. Corrige H5. | P2-15…23. |
| **H6** | Creencias por observador (`BeliefObservation`) y política de decisión. Convierte el draft actual (H7) en un caso particular. | P3-29…32 y G09…G15. |
| **H7** | Vistas de organigrama e histórico, y benchmark de volumen. | G16…G24 y P4-37/38. |

Orden de las dos decisiones que se bloquean entre sí: **H4 depende de H2**
(hacen falta perfiles antes de asignar cargos a personas) y **H4 no depende de
H3** (una persona con perfil de backfill puede ocupar un cargo). Se puede
entregar H4 con generación aún sin factores latentes.

---

## 5. Lo que queda fuera, y por qué

- **LLM por persona o por decisión.** El anexo lo excluye en §0.2 y aquí
  tampoco entra.
- **Fusiones y refundaciones de clubes.** Siguen fuera por la misma razón que
  en el ADR 0007: necesitan un modelo de negociación que no existe.
- **Mercado de fichajes y traspasos.** Es Fase 2, y el anexo §17.3 lo deja ahí.
- **Cohortes poblacionales completas.** H4 reutiliza y materializa personas del
  territorio; la reserva latente por cohortes es Fase 2.
- **La escala económica de afición y asistencia.** Es deuda del FIX V2, no del
  anexo, y está anotada aparte. Ningún hito de aquí la arregla ni la disimula.
