# ADR 0011 — El cuadro se dibuja: tablero de postemporada y cruces declarados

- **Fecha:** 24 de octubre de 2026
- **Estado:** aceptado e implementado
- **Contexto:** petición del usuario sobre la pestaña de postemporada del paso 6
- **Reemplaza:** del ADR 0010, la ruta de una puerta como decisión del usuario;
  del ADR 0009, la deducción del cuadro a partir del número de plazas. Lo demás
  de los dos sigue vigente.

## Problema

El ADR 0010 dejó que el usuario marcara cada puesto como **pase directo** o
**repechaje**, y el ADR 0009 dedujo el cuadro de las plazas: potencia de dos y
las mejores siembras esperando la primera ronda. Las dos cosas juntas producen
exactamente un formato, y el usuario quería dos que no caben en él:

> Por ejemplo, si quiero simular la Champions League, el formato de copa
> antiguo, hago 8 divisiones de 4 equipos. Si lo quiero simular aquí, hago una
> ronda, escojo qué lugares de las divisiones quiero que pasen a esa ronda que
> le pondré de nombre octavos. Después hago otra, automáticamente los ganadores
> irán a esa.
>
> Pero si yo quiero imitarla como en la MLB o NFL, con repechajes, hago una
> ronda, los ganadores de las divisiones **no** van automáticamente a la
> siguiente, van los comodines o de repechaje.

Los dos problemas que eso destapa:

1. **La etiqueta no decidía nada.** `direct` y `wildcard` pintaban un color y
   escribían un motivo, pero quién entraba cuándo lo decidía el cuadro deducido.
   El usuario marcaba «directo» a un campeón de división y el motor lo metía en
   la primera ronda igual, porque las plazas eran potencia de dos. La etiqueta
   prometía un comportamiento que no existía.
2. **Las rondas se deducían de las plazas.** `ceil(log2(slots))`. Con eso no se
   puede expresar una postemporada de la MLB —donde los campeones entran en la
   segunda ronda porque el reglamento lo dice, no porque sobren plazas— ni una
   escalerilla, donde cada ronda incorpora a uno.

## Decisión

### 1. La ruta deja de ser una decisión y pasa a ser una consecuencia

`GateRoute.SEED`: una **entrada neutra**. Lo que significa no lo dice una
etiqueta, lo dicen dos cosas que el usuario sí decide:

- **De dónde sale.** Una puerta con división es el puesto de su división. Una
  puerta sin división (`division: null`) es un puesto **entre los que no pasaron
  por ninguna división**, que es lo que siempre se llamó repechaje.
- **A qué ronda entra.** `Gate.target_round`.

`direct` y `wildcard` siguen existiendo en el modelo: los reglamentos escritos
antes de esto se siguen jugando igual, y su motivo se sigue escribiendo igual.
Lo que desaparece es el control que los ofrecía.

### 2. Las puertas de la tabla general se numeran sobre una sola lista

El ADR 0010 las resolvía en el orden en que se declararon, contando cada una
sobre lo que dejó la anterior. Con una puerta por plaza —que es lo que ahora
escribe el editor, para que cada una lleve su ronda y su orden— eso significaba
que «el 2.º de los restantes» pasaba a valer «el 3.º» en cuanto la plaza
anterior se declaraba aparte: el usuario vería entrar a un club distinto del que
dibujó.

Ahora se resuelve en dos pasadas: primero las puertas de división, y después
**todas** las de la tabla general contra la misma lista de descartados. La
numeración ya no depende de cómo el editor agrupe las puertas.

### 3. `seeding: staged` — el cuadro dibujado es otra autoridad

`PlayoffRules.seeding`:

| Valor | Quién fija la forma del cuadro |
|---|---|
| `auto` | las plazas: potencia de dos y pases directos para las mejores siembras (ADR 0009) |
| `staged` | el dibujo: `round_lengths` dice cuántas rondas hay y cada puerta dice en cuál entra su plaza |

Con `staged`, lo que se valida **no es un logaritmo**: es que el camino cierre.
Ronda a ronda, los que entran por una puerta más los ganadores de la anterior
tienen que ser pares y al menos dos, y la última tiene que dejar un solo
superviviente. La cuenta sale de que, si `e_i` son las entradas de la ronda `i`
y hay `R` rondas, cerrar el camino es `Σ e_i · 2^i = 2^R`. Por eso cuatro plazas
en tres rondas es legítimo —una escalerilla— y seis en tres también.

Se consideró inferir `staged` de que todas las puertas trajeran `target_round`,
y se rechazó: un reglamento diría una cosa y se jugaría otra según un detalle de
sus puertas. La forma del cuadro es una decisión, y se declara.

### 4. La política de cruces, por ronda

`PlayoffRules.round_pairings`, una por ronda:

| Política | Qué hace |
|---|---|
| `high_low` | resiembra por la tabla: el mejor vivo contra el peor vivo. Es la MLB. |
| `adjacent` | resiembra por la tabla y cruza vecinos: 1.º-2.º, 3.º-4.º. |
| `fixed` | **no resiembra**: el ganador de un cruce espera al del cruce de al lado. Es una copa. |
| `draw` | sorteo reproducible: el mismo reglamento da siempre los mismos cruces. |

`fixed` es la que faltaba, y es la que convierte el tablero en un cuadro de copa:
con ella el orden que el usuario arrastra dentro de una ronda **es** el cruce.
Ese orden se guarda en `Gate.order`.

La localía la abre siempre el mejor clasificado de la pareja, se cruce como se
cruce: el cuadro decide quién juega contra quién, la temporada decide quién
recibe.

### 5. Una sola implementación de los cruces

`playoffs.pair_round()` forma los cruces de una ronda, y la usan las tres cosas
que antes los formaban por separado: la primera ronda del cuadro dibujado, las
siguientes (`next_round`) y la previsualización del asistente. La vista del paso
6 no dibuja una maqueta de la política de emparejamiento: llama a la política.

### 6. El tablero

La pestaña de postemporada es un kanban. Primera columna, la competición entera:
todos los puestos de todas las divisiones, más las plazas de la tabla general.
Las demás, las rondas que el usuario añade, nombra y ordena. Una plaza clasifica
porque está en una ronda, y las flechas de cada entrada hacen lo mismo que
arrastrarla, porque arrastrar con el ratón no es accesible.

La pestaña de divisiones deja de decidir clasificación: su insignia pasa a
**informar** de la ronda en la que entra cada puesto. Dos sitios para decidir lo
mismo serían dos respuestas.

## Alternativas descartadas

- **Mantener las etiquetas y añadir las rondas.** Habrían convivido dos modelos
  de lo mismo: la etiqueta diciendo «directo» y el tablero poniendo esa plaza en
  la primera ronda. La etiqueta se va porque su trabajo lo hace la posición.
- **Reimplementar el emparejamiento en el frontend** para dibujar los cruces sin
  esperar al motor. Habría dado una vista instantánea y una segunda verdad sobre
  los cruces. Los recuentos de cada ronda —cuántos juegan y cuántos sobreviven—
  sí se calculan en el editor, porque son una división por dos y hacen falta
  mientras se arrastra; los cruces los trae el motor.
- **Una plaza, una puerta, con la numeración de siempre.** Es lo que destapó el
  defecto de la pasada única. Se arregló el modelo en vez de forzar al editor a
  agrupar puertas por ronda, que le habría prohibido al usuario repartir plazas
  de la tabla general entre rondas distintas.
- **Deducir las rondas del número de entradas por ronda.** Posible —`R` sale de
  la ecuación— pero deja al usuario sin poder declarar una ronda vacía de
  entradas por la que solo pasan ganadores, que es media postemporada.

## Consecuencias

- `RULESET_SCHEMA_VERSION` no cambia de mayor: `seeding`, `round_labels`,
  `round_pairings` y `Gate.order` tienen valor por omisión, y un reglamento sin
  ellos se valida y se juega como antes. Su `checksum` recalculado cambia.
- `edition.playoff_byes` guarda ahora `{"club_id": …, "round": n}`. La forma
  anterior —una lista de identificadores, donde todos entraban en la segunda
  ronda— se sigue leyendo, así que una edición a medio jugar no se rompe.
- `PlayoffFormat.SINGLE_ELIMINATION` había desaparecido del enum al introducir
  `PairingPolicy`, y el formulario lo seguía mandando. Restaurado.
- La tabla de una edición se pide **por fase**. Desde que las fases se encadenan
  hay una clasificación por fase, y la consulta las devolvía todas juntas: una
  liga de ocho clubes en postemporada respondía doce filas con dos primeros
  puestos. `GET /editions/{id}/standings` acepta `?stage=` y por omisión
  responde la de la temporada regular.
- `next_round` ya no descarta en silencio a un participante cuando la ronda
  recibe un número impar: lo rechaza. La validación del editor impide llegar
  ahí, y si se llega es un defecto que hay que ver.
- El taller tiene seis `header`/`footer` —uno por división, uno por ronda, el
  del plantel— y `app.css` da a esas **etiquetas** el aspecto de la cabecera y
  el pie de la página: 18px de relleno, 24px de margen abajo, 40px arriba. Cada
  uno se comía hasta 60px del alto que les hacía falta a las fichas, y con ocho
  entradas en una ronda se veían dos. El componente los devuelve a cero con
  `.league-workbench :where(header, footer)`. La clase puntúa más que la
  etiqueta, así que gana a `app.css`; `:where` no suma nada, así que las reglas
  propias siguen mandando. La otra mitad del problema era `.mini`, una clase
  usada en doce botones del taller que **no estaba definida en ninguna parte**:
  las flechas de cada plaza salían con el tamaño de un botón normal.
