# ADR 0009 — Postemporada con pase directo, y un asistente que dibuja lo que pide

- **Fecha:** 24 de octubre de 2026
- **Estado:** aceptado e implementado
- **Contexto:** cierre de la Etapa 2
- **Se apoya en:** ADR 0008 (divisiones dentro de una competición)

## Problema

Dos cosas, y la segunda la descubrió el usuario usando la primera.

### 1. El cuadro tenía que ser una potencia de dos

`PlayoffRules` rechazaba cualquier número de plazas que no fuera 2, 4, 8 o 16.
Con el ADR 0008 eso dejó de ser una limitación teórica: la configuración más
natural de una competición con dos divisiones —**dos clasificados por división
más dos repechajes**— son seis plazas, y seis no es potencia de dos. El usuario
tenía que redondear su reglamento a cuatro (y dejar fuera a dos clubes que
clasificaron) o a ocho (e inventarse dos plazas).

### 2. El formulario pedía seis números que se multiplican entre sí

Palabras del usuario: «el formulario es muy confuso en cuanto al tema de la
cantidad de partidos, días de descanso, días entre series, vueltas entre
divisiones, las de adentro y afuera».

Tenía razón, y el problema no era la redacción de las etiquetas. El paso del
calendario pide seis cantidades —partidos objetivo, partidos por serie, días
entre series, días de descanso semanal, vueltas dentro de la división y vueltas
fuera— cuyo efecto es **multiplicativo y cruzado**: las dos clases de vueltas
deciden los partidos por club, que con el tamaño de las divisiones deciden las
jornadas, que con los descansos deciden los días de temporada. Pedirle al
usuario que haga esa cuenta de cabeza y luego vea el resultado al final del
asistente es pedirle que programe a ciegas.

## Decisión

### Pases directos derivados, no declarados

`PlayoffRules` deriva cuatro propiedades del número de plazas:

| Propiedad | Qué es | Con 6 plazas |
|---|---|---|
| `bracket_size` | la potencia de dos que cabe a los clasificados | 8 |
| `byes` | clasificados que se saltan la primera ronda | 2 |
| `rounds` | rondas que resuelven el cuadro | 3 |
| `first_round_series` | series de la primera ronda | 2 |

Las mejores siembras son las que esperan, que es lo que hacen las ligas de
verdad. El reglamento sigue siendo estricto donde importa: exige tantas
longitudes de serie como rondas tenga el **cuadro**, no como plazas haya.

`seed_bracket` devuelve ahora `(primera_ronda, esperando)` y `next_round` acepta
a los que esperan e incorpora a todos en la resiembra, de modo que el mejor
clasificado de la temporada regular se cruza con el peor de los que siguen
vivos, sin importar si llegó jugando o esperando.

**Los pases directos se persisten** en `competition_editions.playoff_byes`. No
se derivan de nuevo al construir la segunda ronda porque esa ronda se construye
**otro día del mundo y en otra transacción**: recalcular quién tenía bye a
partir de la clasificación sería frágil y, con divisiones, dependería de volver
a resolver quién clasificó por grupo. La lista se vacía en cuanto entran.

### Un endpoint que calcula, no una fórmula repetida en el navegador

`POST /schedule/preview` recibe los parámetros del asistente y devuelve el
calendario, los cruces y el cuadro que producirían. Lo decisivo es **cómo** lo
hace: llamando a `build_schedule`, `group_sizes` y `seed_bracket`, las mismas
funciones que construyen la competición de verdad. No hay una segunda
implementación en TypeScript que pueda divergir de la del motor, y por eso lo
que la interfaz dibuja no es una estimación: es el calendario.

Tres propiedades que el endpoint cumple a propósito:

- **No escribe nada** y no necesita universo ni competición. Se puede llamar
  cuarenta veces mientras alguien arrastra un control.
- **Los clubes son marcadores** («Club 1», «Club 2») agrupados por el tamaño de
  cada división, porque en ese paso los clubes todavía no existen y quién va a
  cada división lo decidirá el generador por cercanía. Lo que importa en el paso
  es **cuántos** caen en cada una, que es lo que decide el calendario.
- **Un calendario imposible se explica**: devuelve `ok: false` con el mensaje y
  las sugerencias del motor, más el reparto de divisiones para que se vea qué
  hay que corregir, en vez de un error HTTP sin contexto.

### Qué se dibuja

El paso 6 pone los controles a la izquierda y, a la derecha, en vivo:

1. **Resumen**: partidos totales, partidos por club (con el objetivo pedido al
   lado si no coincide), jornadas, días con partido y días de temporada con sus
   fechas.
2. **Reparto por club**: una barra apilada por club con sus partidos dentro y
   fuera de la división, y el número al lado.
3. **Matriz de cruces**: tabla club × club con cuántas veces se enfrentan,
   coloreada por intensidad y por tipo de enfrentamiento. Es lo que hace visible
   de un golpe la asimetría de una división.
4. **Las dos primeras semanas**, día a día, con los días de descanso marcados.
   Aclara a la vez el descanso semanal y los días entre series, que es la pareja
   de controles que más se confundía.
5. **El cuadro de postemporada**: cada clasificado con su ruta —campeón de
   división, segundo, repechaje—, los pases directos marcados y las series de
   cada ronda.

Reglas de forma que se respetan porque esto es una central de control y no un
videojuego: tablas y listas reales en vez de lienzos, navegables con teclado y
legibles por un lector de pantalla; **cada color lleva su número al lado**, así
que el color guía pero nunca informa por su cuenta; y la paleta es la de la
aplicación, dos acentos, sin semáforos nuevos.

## Alternativas descartadas

- **Calcular la previsualización en el navegador.** Sería instantáneo y no
  necesitaría red, pero obligaría a reimplementar `build_schedule`, el reparto
  de divisiones y la siembra en TypeScript. Dos implementaciones de la misma
  regla divergen siempre, y la que vería el usuario sería la equivocada.
- **Previsualizar generando la competición y borrándola.** Escribe en el mundo
  para responder una pregunta hipotética, que es exactamente lo que P4 quitó.
- **Dejar el aviso de texto y mejorar la redacción.** Es lo que había: «el
  objetivo de 44 partidos no se puede repartir en jornadas completas…». El aviso
  es correcto y necesario, y sigue estando; lo que no hace es responder a «¿y
  entonces cuánto durará mi temporada?».
- **Byes declarados por el usuario.** Un campo `byes` en el reglamento sería un
  segundo número que puede contradecir a `slots`. Se derivan, como la cuota de
  la relación del ADR 0004.

## Consecuencias

- Un reglamento guardado con plazas de potencia de dos sigue validando y da el
  mismo cuadro: `byes` vale cero y nada cambia.
- `competition_editions` tiene una columna más. La migración `8a2c6b47e135` la
  añade con `[]` por omisión, así que las ediciones en curso no se ven afectadas.
- El asistente hace una petición por cada cambio de control, con 260 ms de
  espera. En una liga de 30 clubes y muchas vueltas el motor construye más de
  dos mil partidos por llamada; es rápido, pero si algún día molesta, el sitio
  donde recortar es el detalle de la matriz, no la fuente del cálculo.
- Queda por hacer de la Etapa 2 el **repechaje interregional** entre ramas de
  una escalera: hoy el reparto de plazas de ascenso es por cuota y territorio,
  sin eliminatoria entre las ligas alimentadoras.
