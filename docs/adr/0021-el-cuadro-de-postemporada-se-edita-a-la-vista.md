# ADR 0021 — El cuadro de postemporada se edita a la vista

- **Fecha:** 1 de noviembre de 2026
- **Estado:** aceptado e implementado
- **Contexto:** petición del usuario: «en la configuración de las llaves en
  postemporada, a veces, cuando hay varias llaves, no se ve la opción de
  partido de perdedor, es una pequeña sección de abajo, aparte no sé qué
  específicamente haga» y «vamos a trabajar en el diseño UX/UI de la
  configuración de postemporada, porque creo que es un poco incómodo y se
  pueden disponer mejor aún los elementos»

## Problema

El tablero había ido quedándose **sobrio de más**. Una hoja de estilo con un
solo `display: none` escondía, a la vez:

| Oculto | Lo que dejaba de poder hacerse |
| --- | --- |
| `.postseason-toolbar .phase-choices` | cambiar el formato de la postemporada |
| `.path-summary` | ver si el camino al campeonato estaba cerrado |
| `.round-count` | ver cuántos entran y cuántos sobreviven a la ronda |
| `.round-editor-header > .button` | quitar una ronda |
| `.pool-column` | — (sustituida por la tira de abajo, pero seguía en el DOM) |
| `.bracket-key::before/::after` | los cables que hacen que un cuadro parezca un cuadro |

Y las **salidas** de cada llave —a dónde va el ganador, a dónde el perdedor—
vivían dentro del pliegue: sólo existían con la llave abierta, y sólo podía
haber una llave abierta a la vez. Con cuatro llaves en una ronda, la salida del
perdedor era literalmente invisible.

## Decisiones

### D1 — Las salidas son el cableado, no un pie de nota

`.key-outputs` sale del `{#if}` del pliegue: **siempre** se ven, con la llave
abierta y con la llave cerrada. Cada salida dice en una línea a dónde va:

```
⠿ Ganador  → Final · llave 1
⠿ Perdedor → eliminado
```

Una por fila, no dos pastillas que se parten: en una columna de 330 px no caben
al lado.

### D2 — Un perdedor sin conectar está *disponible*, no deshabilitado

Antes la salida del perdedor se dibujaba con `opacity: 0.55`, que es como se
dibuja lo que no se puede usar. Ahora va con borde discontinuo y el color de
acento secundario: se lee como una opción abierta. El texto de la barra lo
explica donde antes decía «al abrir otra, la anterior se cierra»:

> Un perdedor sin conectar queda eliminado; conectarlo es lo que crea el
> partido por el tercer puesto, un repechaje o un cuadro de perdedores.

### D3 — Conectar con un clic, no sólo arrastrando

Arrastrar funciona, pero con varias llaves abiertas es un ejercicio de
puntería. Cada salida lleva un «⋯» que abre su lista de destinos:

```
Enviar a…
  Final · llave 1 · puerto 1 · ocupado
  Final · llave 1 · puerto 2 · ocupado
  Final · cruce nuevo
```

El último destino, **cruce nuevo**, es el que convierte al perdedor en un
partido que todavía no existe —el tercer puesto— en vez de obligarle a desalojar
a alguien de una llave ya dibujada. La lista además *enseña* que la salida se
puede conectar: el arrastre no se anuncia solo.

### D4 — Varias llaves abiertas a la vez

`expandedKey: string | null` pasa a `expandedKeys: Record<string, boolean>`.
Abrir una llave ya no cierra la anterior: se pueden comparar dos llaves y
llevar una salida de una al puerto de la otra sin perderla de vista.

### D5 — Los mandos vuelven a la vista, en una sola banda

El `display: none` desaparece. Formato, recuento del camino y «+ Ronda» —que
estaba duplicado en dos sitios— se juntan en `.postseason-controls`, una sola
tira bajo el titular. Las reglas de cada ronda (serie por omisión y política de
cruces) se mueven del pie de la columna a **debajo de su cabecera**: al fondo
quedaban a alturas distintas en cada ronda y no se leían como suyas.

La tarjeta de llave gana una cabecera que dice **qué llave es y en qué se
juega** sin abrirla (`Llave 3 · MD7`, `Llave 1 · Mini-liga · 6 equipos · pasan
2`); cerrada enseña hasta cuatro participantes —una mini-liga de doce no puede
alargar la columna doce filas— y abierta no enseña ninguno, porque los puertos
de abajo dicen lo mismo y además se pueden mover.

### D6 — La columna del plantel se borra, no se esconde

Las plazas de origen se editan en la tira de abajo desde hace tiempo. La
columna lateral seguía en el DOM, oculta por CSS, recogiendo `drop` que nadie
podía ver. Se borra, y la tira de abajo hereda su papel de papelera: soltar ahí
una plaza la saca del cuadro.

### D7 — El motor aprende qué es una llave de consolación

La parte de verdad del cambio no está en el CSS. Conectar los dos perdedores de
las semifinales a un mismo cruce dejaba el grafo con **dos salidas finales**, y
tanto el validador (`validate_sequence`) como el motor que ejecuta el cuadro
(`sim_service._advance_graph_playoffs`) exigían exactamente una: «debe dejar un
campeón». El editor prometía un partido por el tercer puesto que el reglamento
rechazaba.

`consolation_keys(keys)` resuelve la cuestión con una regla corta:

> Una llave es de consolación cuando **todas** sus entradas son perdedores o
> vienen de otra llave de consolación.

Sus salidas finales no cuentan para hallar al campeón. En cuanto una llave
recibe una plaza directa o el ganador de una llave principal, deja de serlo: la
gran final de un cuadro de doble eliminación —ganador del cuadro principal
contra ganador del de perdedores— sí reparte el título.

La misma regla vive en tres sitios más, porque los tres tienen que decir lo
mismo: el editor (para que «camino cerrado ✓» no mienta), el serializador del
asistente (que descartaba el cuadro entero si quedaban dos salidas) y la
etiqueta de la propia llave, que se marca «consolación» y cuyo ganador va al
«3.er puesto», no a «Campeón».

Y la edición ya no se cierra al conocerse el campeón, sino cuando **todas** las
llaves se han jugado: el tercer puesto se disputa a la vez que la final, y
cerrar antes lo dejaría programado y sin jugar.

## Consecuencias

- Con cuatro llaves por ronda, las ocho salidas se ven sin abrir nada.
- Enviar el perdedor de una semifinal al tercer puesto son dos clics, y el
  cuadro lo dibuja al momento: aparece la llave 2 de la final con «Perdedor de
  llave 1» y «Por definir», y el camino pasa a «incompleto» hasta que el otro
  perdedor también llega. El propio tablero enseña la regla.
- Detalles que sólo se ven mirándolo: la tarjeta con el menú abierto sube de
  plano (todas compartían `z-index: 2` y la de abajo tapaba la lista), el
  centrado de la columna es `safe center` (centrado a secas desbordaba hacia
  arriba y tapaba las reglas de la ronda) y la tarjeta ya no recorta su
  contenido (`overflow: hidden` se comía el menú).
