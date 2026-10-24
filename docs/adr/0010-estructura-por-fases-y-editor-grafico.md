# ADR 0010 — Estructura por fases, divisiones asimétricas y un editor gráfico

- **Fecha:** 24 de octubre de 2026
- **Estado:** aceptado e implementado (con una parte declarada y rechazada a propósito)
- **Contexto:** petición del usuario sobre el paso de calendario y estructura
- **Reemplaza:** el modelo de estructura del ADR 0008 en lo relativo a divisiones
  iguales; lo demás sigue vigente

## Problema

El ADR 0008 dio a una competición divisiones, pero de una sola forma: `count`
divisiones **iguales**, las mismas vueltas para todas, los mismos clasificados
por cada una. Servía para una liga por divisiones simétrica y para nada más.

El usuario lo dijo con sus palabras: quería poder decir «son 10 equipos», ver
una tabla única con esos 10, añadir otra tabla al lado, **arrastrar** equipos de
una a otra, y marcar con colores quién pasa a la postemporada directo y quién
por repechaje. Y lo importante, que no es de interfaz sino de modelo:

> Cada división, piénsalo así, como si fuera un subproceso de la liga, que puede
> ser simétrico con otras divisiones, o no, de ahí la flexibilidad.

Con `count` + `intra_cycles` + `inter_cycles` + `qualifiers_per_group` eso es
imposible de expresar: los cuatro campos son globales. Un editor gráfico sobre
ese modelo habría sido una maqueta bonita que no podía producir nada nuevo.

## Decisión

### 1. La competición es una secuencia de fases

`simulation/competitions/structure.py`. Una fase es de una de dos clases:

| Clase | Qué es |
|---|---|
| `table` | una o varias divisiones jugando round-robin **a la vez**, cada una con sus propias vueltas |
| `bracket` | cruces eliminatorios entre los que llegaron, con sus series al mejor de N |

Una `Division` tiene su clave, su nombre, sus **plazas**, sus **vueltas
internas** y sus **vueltas contra las otras divisiones de su fase**. Nada de eso
es global: seis equipos jugando cuatro vueltas internas junto a cuatro jugando
seis es una estructura legítima, y produce —correctamente— que no todos los
equipos jueguen el mismo número de partidos.

Entre dos divisiones distintas se juegan **las vueltas que pida la que más
pida**. No puede haber dos cifras para el mismo enfrentamiento, y rebajar a la
que pide más sería decidir por ella.

### 2. Las puertas son lo que une una fase con la siguiente

Una `Gate` dice **qué puestos salen y por qué ruta**:

- `{division: "norte", positions: [1, 2], route: "direct"}` → el primero y el
  segundo del Norte pasan directos.
- `{division: null, positions: [1], route: "wildcard"}` → el mejor de **los que
  no han pasado por ninguna puerta anterior** entra por repechaje.

Ese detalle —que una puerta general cuenta sobre los que quedan— es lo que hace
que «repechaje» signifique lo que significa, y se verificó con un caso donde el
segundo de una división entra por repechaje porque su división solo daba una
plaza directa.

La ruta es lo que la interfaz pinta con un color y lo que el motor registra como
motivo de cada clasificado. Y las plazas de la fase siguiente **son** la suma de
los puestos de las puertas: el reglamento rechaza un `playoffs.slots` que no
cuadre con ellas, igual que el ADR 0004 rechaza una cuota declarada dos veces.

### 3. Una sola implementación de «quién clasifica»

`qualifiers_from_groups()` —la función que el motor ya usaba— pasó a ser una
envoltura de `qualifiers_from_gates()`. La forma corta del reglamento se
traduce a fases con `derive_stages()` y recorre **el mismo camino** que una
estructura declarada a mano. No hay dos implementaciones que puedan divergir, y
un reglamento guardado antes de este modelo se juega exactamente igual.

### 4. Compatibilidad: dos formas de declarar, nunca las dos a la vez

`StructureRules` conserva `count`, `groups`, `intra_cycles`, `inter_cycles`,
`qualifiers_per_group` y `wildcards` —la forma corta— y gana `stages`, la forma
completa. Declarar las dos se **rechaza**: dos modelos de la misma estructura
pueden contradecirse.

### 5. El editor

`StructureEditor.svelte`. Arranca con una tabla única de los N equipos de la
competición. Desde ahí:

- `+ Añadir división` crea otra y le presta una plaza de la más grande, para que
  el total siga cuadrando.
- Cada plaza se **arrastra** entre divisiones. Como arrastrar con el ratón no es
  accesible, cada plaza lleva además dos botones `◀ ▶` que la mueven a la
  división vecina, y el nombre de cada división es un campo de texto normal.
- Las vueltas se suben y bajan con `−/+`, con un punto por vuelta: la cifra se
  ve y se cuenta.
- **La insignia de cada puesto cicla** entre no clasifica → directo → repechaje.
  Pulsar un puesto es declarar una puerta, y el color es su ruta.
- El total de plazas se compara con los equipos de la competición y se avisa del
  descuadre, igual que los problemas que devuelve el motor.

Debajo, `SchedulePreview` dibuja lo que esa estructura produce, calculado por
`POST /schedule/preview` con las mismas funciones del motor (ADR 0009).

### 6. Un borrador a medias se muestra, no rompe la vista

Mientras alguien arrastra divisiones, el estado intermedio pasa por
configuraciones que el reglamento no aceptaría —una división vacía, una puerta
apuntando a un puesto que ya no existe—. La vista **no** devuelve 422 en esos
casos: devuelve `ok: false` con la lista de problemas, todos a la vez, y el
editor los enseña. Un error HTTP ahí dejaría la pantalla en blanco justo cuando
el usuario necesita saber qué corregir.

## Lo que se declara y todavía no se juega

Una **segunda fase de tabla** —una liguilla entre los clasificados antes de los
cruces— cabe en el modelo y el motor no la sabe jugar: haría falta una tabla por
fase, no por edición. El reglamento la **rechaza con un mensaje que lo dice**:

> una fase de tabla posterior a la primera todavía no se juega: el motor sabe
> encadenar una fase de tabla con un cuadro de cruces, y rechazar esto es
> preferible a aceptar un reglamento que no se puede simular

Y el editor no ofrece el botón. Es la regla de siempre de este proyecto: el
formulario no propone lo que el motor no ejecuta.

## Alternativas descartadas

- **Un editor sobre el modelo antiguo.** Habría permitido arrastrar equipos y
  pintar colores, pero cualquier estructura asimétrica que el usuario dibujara
  se habría perdido al guardar, porque el reglamento no sabía expresarla. Una
  interfaz que promete lo que el modelo no guarda es peor que un formulario
  honesto.
- **Matriz completa de vueltas entre divisiones.** Daría control total —Norte
  contra Sur dos veces, Norte contra Este una— a cambio de una tabla de N×N que
  nadie quiere rellenar. `inter_cycles` por división con la regla del máximo
  cubre lo que se usa; si algún día hace falta la matriz, el sitio donde entra
  es `Stage.cycles_between`.
- **Puertas por equipo en vez de por puesto.** En este paso los equipos no
  existen todavía: lo que se marca es «el primero de esta división», no «este
  club». Marcar clubes exigiría generar el mundo antes de decidir las reglas,
  que es justo lo que P4 separó.
- **Mantener `qualifiers_per_group` como camino rápido en el motor.** Habría
  dejado dos implementaciones de la clasificación. La forma corta ahora se
  traduce y se resuelve por puertas.

## Consecuencias

- `RULESET_SCHEMA_VERSION` no cambia de mayor: `stages` tiene valor por omisión
  y un reglamento viejo sigue validando y jugándose igual. Su `checksum`
  recalculado cambia, como ya pasó con `season.offseason_days`.
- `build_schedule` acepta `cycles_between(a, b)`. Cuando todas las parejas
  juegan lo mismo, el calendario sigue delegando en el round-robin clásico, que
  reparte mejor jornadas y localías; la rama asimétrica solo entra cuando hace
  falta.
- La vista de la edición lee la estructura con su propio modelo y no a mano.
  Mirar `rules_json["structure"]["count"]` dejaba la ficha en blanco con fases
  declaradas, y ese fallo apareció al probar el ciclo completo.
- Queda pendiente, además de la fase intermedia de tabla, el **repechaje
  interregional** entre ramas de una escalera, que es el último punto abierto de
  la Etapa 2.
