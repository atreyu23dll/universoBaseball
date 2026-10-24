# ADR 0008 — Divisiones dentro de una competición

- **Fecha:** 23 de octubre de 2026
- **Estado:** aceptado e implementado
- **Contexto:** cierre de la Etapa 2 (especificación maestra §5: «grupos,
  divisiones y conferencias dentro de una misma competición»)
- **Se apoya en:** ADR 0004 (frontera de temporada y autoridad de la cuota)

## Problema

Hasta aquí toda competición era **una tabla única** con un round-robin
uniforme: todos jugaban contra todos el mismo número de veces y clasificaban
«los mejores N». Eso descarta de un golpe la forma que tienen casi todas las
ligas de béisbol reales —divisiones Este/Oeste, conferencias, zonas Norte/Sur—
y, con ella, tres cosas que importan al ecosistema:

- **La geografía de los viajes.** Si todos juegan contra todos lo mismo, el
  coste de transporte de un club es el mismo esté donde esté. Las divisiones
  existen en parte porque viajar cuesta.
- **El valor de la rivalidad cercana.** Jugar dieciocho veces contra el vecino y
  seis contra el del otro extremo del país no es un detalle de calendario: es lo
  que hace que una división signifique algo.
- **Quién clasifica.** «Los cuatro mejores» y «los campeones de cada división
  más dos repechajes» producen postemporadas distintas, y la segunda es la que
  permite que un club de un grupo flojo entre con peor registro que uno que se
  queda fuera.

## Decisión

Un bloque nuevo del reglamento, `structure`, y cuatro consecuencias en el motor
puro. `count = 1` es el comportamiento anterior, bit a bit.

### 1. El reparto lo hace el motor, no el formulario

`simulation/competitions/groups.py`. El usuario declara **cuántas** divisiones
hay y con qué criterio, nunca qué club va a cada una —cuando se escribe el
reglamento los clubes todavía no existen—:

- `geographic` (por omisión): se toma el club más alejado del centro de la
  competición como origen de un grupo y se le añaden sus vecinos más próximos
  hasta llenarlo; se repite con los que quedan. Produce divisiones compactas, es
  determinista y cada club lleva escrito a cuántos kilómetros de la sede del
  grupo está.
- `balanced`: serpiente por recursos (1-2-3-3-2-1), para que ningún grupo
  acumule a los clubes ricos. Es una decisión de competitividad y se declara
  como tal, no se disfraza de geografía.
- `declared`: el usuario pone nombres y plazas; el llenado sigue siendo por
  cercanía.

Un reparto que no cuadra —plazas declaradas que no suman los clubes que hay— se
**rechaza**. No se mete un club de relleno para completar un grupo.

### 2. El calendario es asimétrico, y eso tiene consecuencias que se dicen

`intra_cycles` vueltas contra los del grupo, `inter_cycles` contra los demás.
Dos efectos que no se esconden:

- **Los partidos por club dejan de ser una entrada.** Pasan a ser una
  consecuencia de las vueltas declaradas. `season.games_per_club_target` sigue
  existiendo como objetivo, y el motor avisa de la diferencia en vez de ajustar
  las vueltas por su cuenta.
- **Con grupos de tamaños distintos, no todos juegan lo mismo.** Un club de un
  grupo de tres tiene menos rivales cercanos que uno de un grupo de cinco. Se
  advierte y se recuerda que la clasificación usa porcentaje de victorias, que
  no depende del número de partidos.

### 3. Las localías, por orientación euleriana

Repartir quién es local en un enfrentamiento que se juega **una sola vez** no es
trivial. Dos intentos descartados, en este orden:

| Intento | Resultado medido (16 clubes, 4 divisiones, una vuelta cruzada) |
|---|---|
| Local el primero de la lista | desbalance de 24 partidos |
| Local «el que menos veces lo ha sido» (voraz) | desbalance de 24 partidos |
| **Orientación euleriana** | **desbalance de 0** |

El problema es exactamente orientar las aristas de un grafo para que cada
vértice tenga el mismo número de salientes que de entrantes, y eso lo resuelve
un recorrido euleriano: si todos los grados son pares, el circuito entra y sale
de cada club el mismo número de veces. Los clubes con un número impar de
rivales se conectan a un vértice virtual para que el circuito exista, y su
desajuste queda en uno, que es el mínimo posible. El reparto voraz parece
equivalente y no lo es: procesa los enfrentamientos en orden y acaba dando casi
todos los partidos en casa a los últimos clubes de la lista.

Las vueltas pares no necesitan nada de esto: se reparten exactas, la mitad en
cada campo.

### 4. Una tabla por club, mirada por divisiones

La clasificación **no** se recalcula dentro del grupo: sigue habiendo una fila
por club con todos sus partidos, y el grupo solo añade `group_rank`, que es el
orden general restringido a sus miembros. Es como se publican las divisiones de
verdad, y evita la pregunta sin respuesta de qué hacer con los partidos
intergrupo en una tabla de división.

### 5. La estructura es la autoridad única de las plazas de playoff

Con divisiones, `playoffs.slots` deja de ser un número que el usuario elige:
vale `count × qualifiers_per_group + wildcards`. Un reglamento que declare otro
se rechaza diciendo cuál cuadra, y el asistente muestra la cifra en vez de un
selector. Es la misma regla del ADR 0004 —no existen dos números que puedan
contradecirse— aplicada aquí.

Cada clasificado guarda su **ruta**: `group_winner` con su puesto de división,
`wildcard` con el motivo, y queda en un evento del universo.

### 6. El grupo vive en la inscripción, no en el club

`edition_entries.group_key`, por edición. El reparto se rehace al abrir cada
temporada con los clubes que hay, porque los ascensos, los descensos y las
desapariciones cambian el mapa: una división heredada del año anterior dejaría a
alguien sin rivales. Un club que asciende entra en la división que le toca por
geografía sin que nadie lo coloque a mano y sin dejar de ser el mismo club.

## Alternativas descartadas

- **Un grupo = una competición vinculada.** Se podría modelar la Este y la Oeste
  como dos competiciones hermanas con una relación. Se descartó: comparten
  reglamento, temporada, campeón y tabla general, y separarlas obligaría a
  inventar un tipo de relación «mismo torneo» que tendría que replicar todo lo
  que ya hace una competición.
- **Tabla de división calculada solo con partidos intragrupo.** Es defendible y
  produce una pregunta sin respuesta buena: qué pasa con los partidos cruzados,
  que entonces no cuentan para nada. Las ligas reales cuentan todos.
- **Coloreado de aristas óptimo para las jornadas.** El empaquetado voraz que se
  usa cuando las vueltas son asimétricas gasta entre un 10 % y un 25 % más de
  jornadas que el mínimo teórico. Son días de más de temporada, no inequidad, y
  arreglarlo pide un algoritmo de coloreado que no justifica su complejidad
  todavía. Queda dicho en el módulo. Cuando las vueltas dentro y fuera
  coinciden, el calendario es el round-robin de siempre y el problema no existe.

## Consecuencias

- `RULESET_SCHEMA_VERSION` no cambia de mayor: `structure` tiene valor por
  omisión (`count = 1`) y un reglamento guardado sigue validando. Su `checksum`
  recalculado sí cambia, como ya pasó con `season.offseason_days`.
- Las ediciones ya jugadas quedan con `group_key` vacío, que es exactamente lo
  que fueron: competiciones de tabla única.
- Los playoffs siguen limitados a potencias de dos, así que un cuadro de seis
  —dos campeones de división con bye y cuatro repechajes— no se puede sembrar
  todavía. Es lo siguiente de la Etapa 2.
