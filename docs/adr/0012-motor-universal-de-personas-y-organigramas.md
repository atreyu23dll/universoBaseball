# ADR 0012 — Motor universal de personas y organigramas procedurales

- **Fecha:** 25 de octubre de 2026
- **Estado:** aceptado. D1, D2 y D4 implementados en H1 y H2
  (`simulation/persons/`, `person_universal_profiles`, `person_service`); D3 y
  D5 pendientes de H4
- **Contexto:** `Baseball_Universe_Personas_Organigramas_v1_1.md`, anexo técnico
  v1.1, y la auditoría [H0](../personas-h0-auditoria.md)
- **Se apoya en:** ADR 0003 (RNG derivado por contexto), ADR 0005 (economía de
  abajo arriba), ADR 0007 (vida institucional)

## Problema

El anexo pide que toda persona del universo comparta una plantilla de 52
atributos, que las relaciones entre personas sean aristas dirigidas y que cada
club pueda organizarse en departamentos anidados con personas asignadas N:M.

La auditoría midió la distancia real, y no es la que parecía. No es «añadir 46
atributos»: es que **hoy no existe ninguna persona que no sea un jugador**
([people.py:299](../../simulation/generation/people.py#L299)), los cargos de un
club son cadenas de texto sin titular
([organization.py:233](../../simulation/generation/organization.py#L233)), de los
seis números psicológicos que se guardan **solo uno se lee** en toda la base de
código ([rates.py:118](../../simulation/baseball/rates.py#L118)), y las personas
pertenecen a la edición que las creó y no al universo
([people.py:413](../../simulation/generation/people.py#L413)), así que dos ligas
en la misma ciudad generan dos poblaciones que no se conocen.

Son cuatro problemas distintos con cuatro riesgos distintos. Este ADR fija cómo
se abordan antes de escribir la primera tabla.

## Decisiones

### D1 — El perfil universal va en una tabla propia, en JSONB versionado

`person_universal_profiles(universe_id, person_id)` con `profile_data` JSONB
validado por Pydantic al escribir, más `profile_schema_version`,
`generated_seed` y `parameter_version`.

No se añaden 52 columnas, y tampoco se mete el perfil dentro de
`people.attributes`, que es donde viven los bloques de béisbol. La separación es
la del anexo §13: **el núcleo humano y las competencias de dominio son cosas
distintas**, y `people.attributes` ya es, de hecho, el `BaseballSkillProfile`
con otro nombre. Dejarlos en tablas distintas permite que exista una persona con
perfil universal y sin competencia deportiva alguna —un tesorero que no juega—,
que es justo lo que hoy es imposible.

La validación es obligatoria al escribir, no recomendada: una `Person` activa
sin sus 52 valores es un estado prohibido, y el servicio que crea personas es
transaccional o idempotente (§15.5).

### D2 — `Cognition` sobrevive como vista derivada, y `composure` no se vuelve a sortear

Los seis números actuales se absorben en los 52 por identidad, no por sorteo
nuevo: `competitiveness`, `risk_tolerance` y `sociability` tienen el mismo
nombre en el catálogo; `learning` pasa a `learning_rate`; `work_ethic` pasa a
`conscientiousness`; `composure` pasa a `inhibitory_control`.

Y `Cognition` **no se borra**: queda como proyección de lectura sobre el perfil
universal, con los mismos seis nombres, para que `simulation/baseball` no
cambie una línea. La razón no es comodidad: `composure` es el único de los seis
que entra en el motor de partidos, así que preservar su valor exacto es lo que
mantiene reproducibles los partidos ya jugados. Una prueba con semilla fija
sobre un partido completo lo vigila.

### D3 — Los cargos pasan a tablas con persona, y el JSON del club queda como proyección

`clubs.organization.roles` **deja de ser la fuente de verdad** y pasa a ser una
vista derivada de `organization_units`, `organization_positions` y
`organization_role_assignments`.

Se descartó ampliar el JSON. Lo que el anexo §23.5 exige por asignación
—`person_id`, unidad, función del vocabulario versionado, autoridad concedida,
carga horaria, intervalo con estado, relación laboral, histórico que no se
sobrescribe— no cabe en un documento del club sin reinventar en JSON lo que una
tabla ya resuelve, y además haría imposible la consulta que el anexo pide en
primer lugar: «todos los cargos de esta persona», que atraviesa clubes.

Lo que **sí se conserva** de lo que hay, porque ya decide bien:

- `GovernanceModel` íntegro. El §23.7 paso 2 pide exactamente eso —decidir el
  gobierno antes del organigrama— y ya está implementado y probado.
- La lógica de `assign_roles` que reparte un presupuesto de meses de personal y
  deja puestos remunerados, voluntarios o **vacantes**. Un puesto vacante es un
  estado legítimo (§23.4 G07) y el código ya lo sabe.
- El patrón de `RosterAssignment`: vínculo persona ↔ club con intervalo y
  estado. Las asignaciones de cargo son lo mismo con unidad, función y
  autoridad añadidas.

Lo que se corrige: `doubles_with`, que hoy apunta al nombre de otro cargo, pasa
a ser lo que siempre quiso decir —la misma persona ocupando dos asignaciones—, y
deja de necesitar un campo propio.

La proyección JSON se mantiene mientras la ficha de club
([+page.svelte:160](../../frontend/src/routes/clubes/%5Bid%5D/+page.svelte#L160)) y el
preview ([competition_service.py:424](../../backend/app/application/competition_service.py#L424))
la consuman. Se retira cuando el frontend lea el organigrama, no antes.

### D4 — Las personas pasan a ser del universo, sin reescribir a las que ya existen

La clave de una persona deja de derivarse de la edición y pasa a derivarse de su
territorio y su cohorte. El servicio que necesita gente —fundar un club, cubrir
un cargo, llenar una plantilla— **busca primero** entre quienes ya existen y
solo materializa a alguien nuevo cuando el territorio lo justifica.

Las personas ya creadas **conservan su clave actual**. No se renombran, no se
fusionan y no se deduplican retroactivamente: sus partidos, sus estadísticas y
sus plantillas dependen de esa clave, y el principio del proyecto es que el
pasado no se sobrescribe. Un universo viejo seguirá teniendo poblaciones
disjuntas por edición; los universos nuevos, no. Esa asimetría es una
consecuencia aceptada y se dice en la interfaz, no se disimula.

La semilla de cada persona se deriva de su identidad y de la versión del
esquema (ADR 0003), nunca del orden de iteración de una consulta ni del índice
dentro de un bucle.

### D5 — El orden de génesis se extiende, no se reordena

La cadena causal del ADR 0005 se mantiene intacta —territorio → recursos finitos
→ organización → instalación → cuentas → nivel efectivo— y las personas se
insertan donde el anexo §12.1 las pide, **entre las cuentas y el reparto de
plantillas**:

```text
… → cuentas de abajo arriba
      → funciones que el reglamento y el contexto exigen
        → unidades que se justifican
          → personas responsables (reutilizadas o materializadas)
            → reparto de plantillas
              → nivel efectivo
```

Esto no es una concesión al orden existente: es que `paid_staff_months`, el
presupuesto de personal que hoy decide cuántos cargos se pueden pagar, **sale de
las cuentas**. Decidir el organigrama antes del dinero sería volver a la
causalidad que el FIX V2 prohíbe: una etiqueta de competición repartiendo
estructura.

## Alternativas descartadas

- **52 columnas en `people`.** Cada cambio del catálogo sería una migración de
  esquema, y el anexo prevé explícitamente que el catálogo crezca por versión.
- **Meter el perfil universal en `people.attributes`.** Mezcla el núcleo humano
  con las competencias de béisbol y hace imposible una persona sin deporte.
- **Ampliar `clubs.organization.roles` con un `person_id`.** Resuelve el caso
  fácil —un cargo, un titular— y deja fuera unidades anidadas, varias personas
  por unidad, autoridad, carga y, sobre todo, la consulta por persona.
- **Deduplicar retroactivamente las poblaciones por edición.** Obligaría a
  decidir qué dos jugadores «son la misma persona» sin ninguna evidencia, y a
  reescribir estadísticas ya registradas.
- **Generar los 52 atributos como independientes.** Prohibido por §9.1 y ya
  presente como defecto a escala de seis. Entra con factores latentes en H3.
- **Materializar una persona por nodo del organigrama.** Es el antipatrón
  explícito de §21 y produciría clubes llaneros con cinco empleados ficticios.

## Consecuencias

- Aparecen personas que no juegan. Todo lo que hoy asume que una persona es un
  jugador —la ficha, los listados, las consultas— tiene que admitir que no lo
  sea. `primary_position` y `pitcher_role` pasan a ser opcionales de hecho,
  aunque la columna siga existiendo.
- La ficha de un club pasa de mostrar seis responsabilidades anónimas a mostrar
  un árbol con titulares. Es el cambio visible del hito H4.
- El determinismo se conserva donde se puede comprobar: misma semilla, misma
  versión y mismo contexto siguen dando la misma ficha, pero las claves de
  persona de los universos nuevos no coinciden con las de los viejos.
- El volumen de escritura crece y hay que medirlo antes de ampliarlo. El anexo
  fija el límite en una frase que este ADR adopta: no se escriben los 52
  atributos de cada persona en cada tick.
- Nada de esto se declara implementado hasta que sus pruebas pasen. Son 64
  criterios de aceptación entre P0–P4 y G01–G24, y el anexo prohíbe cerrarlos
  simplificando lo que comprueban.

## Estado de cada decisión

| | Decisión | Estado |
|---|---|---|
| D1 | Perfil universal en tabla propia, JSONB versionado | **Hecho** — `person_universal_profiles`, validado con Pydantic al escribir y al leer |
| D2 | `Cognition` como vista derivada; `composure` no se vuelve a sortear | **Hecho a medias** — el backfill ya conserva los seis números (`LEGACY_COGNITION_MAP`); la vista derivada que sustituya a `Cognition` llega cuando el generador de jugadores lea del perfil universal |
| D3 | Cargos en tablas con persona; el JSON del club como proyección | Pendiente (H4) |
| D4 | Personas del universo, sin reescribir a las que existen | **Hecho** — `materialize_person` y `available_people`. Desde el ADR 0013 es además la **única** puerta: ninguna competición crea gente. Los jugadores de universos anteriores conservan su clave con identificador de edición |
| D5 | El orden de génesis se extiende, no se reordena | Pendiente (H4) |

Una consecuencia que no estaba prevista y conviene dejar escrita: para que una
persona pudiera existir sin ser jugadora hubo que **relajar siete columnas** de
`people` —papel, posición, lateralidad al bate y al guante, estatura, peso y
valoración global—, que eran obligatorias. El esquema afirmaba que toda persona
del universo juega al béisbol, y nadie lo había notado porque el generador solo
sabía crear jugadores. El `default="player"` de la columna del papel heredado
también tuvo que irse: convertía en jugador a quien se insertaba sin papel, que
es exactamente a quien no lo es.

**Nota del 25/10/2026.** El ADR 0013 retiró la generación de plantillas. Eso no
cambia ninguna de estas cinco decisiones, pero sí su alcance: D2 queda en
espera —`Cognition` solo se lee en el backfill de jugadores de universos
anteriores, porque ya no se generan jugadores nuevos— y la asimetría que D4
aceptaba (universos viejos con poblaciones por edición, nuevos sin ellas) pasa a
ser que los universos nuevos **no tienen jugadores en absoluto** hasta que
exista la mecánica de selección.
