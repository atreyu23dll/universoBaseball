# ADR 0014 — Organigrama procedural de cada club

- **Fecha:** 26 de octubre de 2026
- **Estado:** aceptado; fundación implementada, crecimiento pendiente
- **Contexto:** plantilla de organigrama definida por el usuario; anexo de
  personas §23
- **Se apoya en:** ADR 0012 (motor universal de personas) y ADR 0013 (retirada
  de la generación de plantillas)

## Problema

Hasta ahora un club decía tener responsabilidades —`organizador`, `manager`,
`tesorero`— y no eran de nadie: cadenas de texto en una columna JSON, con
`doubles_with` apuntando al **nombre de otro cargo** en vez de a una persona
(auditoría H0, hallazgo H6). La ficha mostraba siete casillas y detrás no había
un solo habitante del universo.

La plantilla que el usuario definió pide otra cosa: cinco familias funcionales
divisibles en subdivisiones sin límite de profundidad, personas que pueden
estar en varias unidades a la vez, cargos que pueden quedar vacantes y
funciones que se pueden compartir. Y una regla que cambia el resultado más que
todas las demás: **primero existen las necesidades y las responsabilidades;
después se crean los departamentos o cargos necesarios para atenderlas.**

## Decisiones

### D1 — Tres tablas, y ninguna columna nueva en `clubs`

`organization_units` (árbol), `organization_positions` (cargos) y
`organization_role_assignments` (personas). El organigrama no es un campo del
club: es una estructura con su propia historia, que crece, se fusiona y se
cierra sin reescribir el pasado.

`clubs.organization` se queda donde está, con el gobierno, la sede y el alcance
que el club se dio. Lo que **deja de ser** fuente de verdad es su lista de
`roles`: ahora las responsabilidades están en las tablas, con titular, autoridad
y carga.

Las tres llevan `reason`. Sin eso, la regla de «primero las necesidades» no se
puede comprobar: una unidad que no dice qué necesidad la justificó es un dibujo.

### D2 — La jerarquía sale del código de la unidad

Los códigos del catálogo son jerárquicos —`sports.staff.pitching`— y de ahí se
deduce el padre. Así la jerarquía no se declara dos veces y no puede
contradecirse consigo misma. La profundidad no está limitada por el modelo: el
catálogo ya trae cuatro niveles (club → Deportivo → cuerpo técnico →
entrenadores de pitcheo) y añadir más es añadir un punto.

Cada club tiene una **raíz técnica** que lleva su nombre y no pertenece a
ninguna familia: no es un área, es la institución. La tienen también los clubes
sin departamentos.

### D3 — Al fundarse, un club crea lo que necesita y nada más

Un club recién fundado recibe su raíz, su **Gerencia** y el cargo que encabeza
su gobierno. No recibe los otros cuatro departamentos.

No es una simplificación: es la regla de la plantilla aplicada. Un club que
acaba de nacer no tiene jugadores que dirigir, ni patrocinios que negociar, ni
estadio propio que mantener. Instanciar las cinco familias el primer día y
poner a alguien en cada una sería rellenar un organigrama corporativo con
empleados ficticios, que es exactamente el antipatrón que el anexo §21 prohíbe.

Los demás departamentos aparecerán cuando haya trabajo que los justifique. Que
el catálogo los contenga no los crea.

### D4 — Propiedad y representación no son lo mismo

Las tres formas de gobierno con propietario —proyecto familiar, sociedad
deportiva, franquicia— reciben un cargo `club_ownership` con autoridad para
representar, inscribir, **firmar y gastar**. Una sociedad deportiva admite
hasta tres socios; un proyecto familiar, uno.

Las otras seis no las posee nadie, y lo que tienen es `club_representation`:
coordinación de un colectivo, presidencia de una asamblea, patronato,
responsable municipal o del programa escolar, representante del negocio que lo
respalda. Puede representar al club e inscribirlo; lo que toca al dinero pasa
por el órgano que lo gobierna.

La autoridad es una **concesión del cargo**, no un rasgo de la persona: querer
mandar no da permiso para gastar, y `assign_person` rechaza conceder a una
asignación autoridad que su puesto no tiene. Se puede recortar o delegar; nunca
inventar.

### D5 — Quien encabeza un club es una persona del universo, sin excepción

Sale de `person_service.materialize_person`: tiene sus 52 atributos, vive en el
territorio del club y su ficha no se distingue de la de cualquier otro
habitante. **Lo que la hace propietaria es la asignación**, no su perfil. No
existe una clase de persona «dueño» con rasgos propios, y el generador no sabe
nada de propiedad cuando la crea.

Su edad sale de `FOUNDER_AGE_RANGE` (31–64), declarado como heurística: es el
tramo donde alguien ya ha tenido tiempo de reunir lo que hace falta para fundar
algo. No es una regla del mundo real y está donde se puede discutir.

## Alternativas descartadas

- **Instanciar las cinco familias en todos los clubes.** Es lo que la plantilla
  prohíbe de forma más explícita, y produce clubes llaneros con cinco
  departamentos y un empleado en cada uno.
- **Guardar el organigrama como JSON dentro del club.** Resuelve el dibujo y no
  la pregunta que la plantilla hace primero —«todos los cargos de esta
  persona»—, que atraviesa clubes y no cabe en un documento por club.
- **Crear una persona por nodo del organigrama.** Antipatrón explícito del
  anexo §21: las unidades existen para alojar responsabilidades, no para
  consumir empleados.
- **Derivar la autoridad de los rasgos de la persona.** Confunde preferencia
  con permiso. `dominance_preference` alto no firma un contrato.

## Consecuencias

- **Un universo nuevo tiene habitantes desde el primer día.** Crear una liga de
  doce clubes crea doce o algunas más personas —según cuántos socios tenga cada
  sociedad deportiva—, todas con sus 52 atributos y ninguna jugadora.
- **La ficha del club sirve y muestra su organigrama.** La API lo da en
  `chart` —el árbol, los cargos con los vacantes marcados, y las personas una
  sola vez con todas sus responsabilidades y su carga semanal sumada— y la
  pantalla lo pinta como árbol, con cada ocupante enlazado a su ficha. La lista
  anónima de `organization.roles` dejó de mostrarse.
- **La ficha de una persona muestra sus 52 atributos**, agrupados en las tres
  dimensiones, cada uno con su nombre legible y su **clase** —rasgo, estado,
  capacidad, tendencia—, porque un estado de hoy y un rasgo de siempre no se
  leen igual. Los nombres legibles viajan desde el catálogo de Python, no
  escritos a mano en la interfaz (ADR 0012, R5). Y con ellos van sus cargos, con
  el club, la unidad y lo que el puesto le autoriza a decidir.
- Lo que se muestra se presenta como lo que es: **parámetros de una ficción
  simulada**, no una medida de nadie. El anexo §16.3 reserva los 52 valores
  reales para una vista de observación, y esta lo es: el usuario es el
  observador del universo, no un actor que pueda usarlos para decidir.
- **`clubs.organization.roles` queda obsoleto** y pendiente de retirar: ya no lo
  lee la interfaz, solo la previsualización de una competición.
- **Lo que no hace todavía:** crear departamentos cuando aparece el trabajo,
  fusionarlos en una crisis, cerrarlos, mover una unidad de rama o delegar
  autoridad. El modelo lo admite —las tablas tienen estado, temporada de
  creación y de cierre— y los eventos institucionales (`ORG_UNIT_CREATED`,
  `ORG_UNIT_MERGED`, `ROLE_ASSIGNED`…) no están emitiéndose.
- **Reproducibilidad, dicho con precisión:** el organigrama de un club se
  siembra con su clave, así que dentro de un universo es estable. Entre dos
  universos con la misma semilla maestra **no** coincide, porque la clave de un
  club lleva dentro el identificador de su edición, que es aleatorio. Es
  anterior a este ADR y afecta a todo el camino del backend; en la simulación
  pura, donde la clave de edición es un argumento, el mundo sí es reproducible.
