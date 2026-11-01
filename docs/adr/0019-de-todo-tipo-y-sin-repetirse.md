# ADR 0019 — De todo tipo, y que no se repitan

- **Fecha:** 31 de octubre de 2026
- **Estado:** aceptado e implementado
- **Contexto:** petición del usuario: «de verdad quiero que se generen escudos
  deportivos creativos, y no sólo sacarlos de una lista. Quiero que haya de todo
  tipo, de todo tipo, que sea muy muy complicado que se generen dos [iguales]»
- **Se apoya en:** ADR 0017 (silueta procedural y blasón por capas) y ADR 0018
  (símbolos paramétricos y arquetipos de marca)

## Problema

Los dos ADR anteriores arreglaron el escudo heráldico, y al medirlo salieron
dos cosas incómodas:

1. **88 de cada 100 marcas eran escudos heráldicos.** En
   `build_identity_system` la dirección heráldica pesaba **16,0** y las cinco
   rotuladas entre 0,15 y 0,2: una proporción de 60 a 1. La familia que de
   verdad usa el béisbol —wordmark, parche de gorra, monograma— salía **2 veces
   de cada 100**.
2. **Y esas cinco direcciones eran cinco recetas.** `heritage`, `athletic`,
   `seal`, `ligature` y `pennant` tenían las cajas escritas a mano: monograma
   siempre arriba en `(41, 9, 59, 28)`, rótulo siempre en `(6, 33, 94, 65)`,
   ciudad siempre en `(25, 85, 78, 91)`. Cien clubes se repartían en cinco
   grupos reconocibles.
3. **El criterio de aceptación protegía el problema.** La prueba de la galería
   exigía `styles["heraldic"] >= 65`: la falta de variedad estaba escrita como
   requisito.
4. Faltaban dos cosas que el usuario había señalado antes: las **iniciales
   dentro del escudo** —lo más característico de un escudo de club de fútbol— y
   el **empuje diagonal** con figura de perfil de las marcas norteamericanas.

## Decisiones

### D1 — La marca rotulada es un sistema, no cinco recetas

`lettering_lockup` compone por piezas, y cada una se sortea:

| Pieza | Repertorio |
| --- | --- |
| Marco | ninguno, roundel, **escudo**, cápsula, banderín |
| Monograma | arriba, dentro, **detrás** (grande y velado), ninguno |
| Rótulo | recto o en arco, dos tipografías, con sombra desplazada o sin ella |
| Adorno | ninguno, swash, barra, doble barra, estrellas, rombos |
| Pie | plaza, año de fundación, en arco sobre el roundel, ninguno |

El escudo está entre los marcos a propósito: **un rótulo dentro de un escudo es
exactamente la marca de un club de fútbol europeo**, y era lo único que el motor
no sabía hacer.

Las piezas se reparten en franjas con `_stack`, así que las proporciones también
varían. El estilo ya no fija nada: **inclina** —`seal` tiende al roundel,
`pennant` al banderín, `ligature` al monograma grande— y el resto se sortea.

### D2 — Regla de tinta: dentro y fuera del marco

Dentro de un marco, el fondo **es** el color del club, así que la letra va
clara; fuera, la marca se dibuja sobre la página y la letra va del color del
club con perfil claro. Rotular en `field` sobre un marco de `field` dejaba la
marca entera invisible menos el contorno, y así salían muchas.

### D3 — Reparto deliberado de direcciones

Los pesos pasan a ser una tabla legible que la personalidad del club inclina:
un club arriesgado tira a `athletic`, uno comunitario a `seal` o `heritage`, uno
ambicioso a `ligature`. Resultado sobre las cien identidades de la galería:

| Dirección | Antes | Ahora |
| --- | --- | --- |
| heraldic | 88 | 34 |
| symbolic | 10 | 18 |
| athletic / seal / ligature / heritage / pennant | 2 en total | 48 en total |

**Criterio de aceptación cambiado a propósito**: donde la prueba exigía «al
menos 65 de cada 100 heráldicas», ahora exige lo contrario —seis direcciones o
más, ninguna por encima de 45, el escudo al menos 20 y la familia rotulada al
menos 25—. Queda anotado en la propia prueba: el criterio viejo *enshrinaba* la
falta de variedad.

### D4 — Dos arquetipos más

- **Escudo de iniciales** (`blasón monograma`): las letras del club en el punto
  de honor, con su figura pequeña en jefe o en punta. Es el cuarto arquetipo
  heráldico, junto a simple, cuartelado y acompañado.
- **Marca con empuje**: banda diagonal recortada y figura inclinada, con el
  rótulo viajando sobre la banda. Es el gesto de una marca norteamericana —
  asimétrica y con prisa—, lo contrario de la heráldica, y por eso es un
  arquetipo propio y no una variante.

### D5 — La fauna mira de lado

`bird` y `bull` tienen ahora **dos vistas**: la frontal heráldica y la **cabeza
de perfil** —pico ganchudo con ceja y cresta barrida; morro, testuz y cuerno
barrido hacia atrás—. La vista se declara en el nombre del nodo
(`symbol:bird:perfil`), que es lo que permite comprobarla y explicarla.

Se aprendió por las malas: una cabeza de perfil **no** sale de encadenar curvas
paramétricas de la punta a la nuca —eso da un hocico de foca—, sino de la lista
de puntos de la anatomía en orden, y de que el pico o el morro **sobresalgan**
contra una masa de cabeza alta.

### D6 — La marca reducida dibuja menos, no el doble

Por debajo de 64 píxeles el servicio sirve la variante `reduced`, y ésta llevaba
**dos pasadas** de contorno sobre el monograma: más elementos que la principal,
y a ese tamaño una mancha. Ahora es una sola pasada con perfil grueso.

## Consecuencias

**Medido.**

| Qué | Resultado |
| --- | --- |
| 1.000 escudos heráldicos del **mismo** club, sólo cambia la semilla | **1.000 estructuras distintas** |
| 1.000 marcas completas (todas las direcciones) del mismo club | 960 estructuras distintas |
| 1.000 **clubes distintos** | **1.000 marcas exactas distintas**: ninguna repetida |
| Galería de aceptación | 100 de 100 con estructura distinta, 7 direcciones, ninguna por encima del 34 % |

**Lo que cuesta.** La dirección de arte deja de ser predecible: un club puede
recibir un escudo blasonado o un wordmark con monograma, y eso es justo lo
pedido. Quien quiera un escudo para todos tiene el parámetro `design_style`.

**Límites declarados.**

- **`compose_identity_logo` sin estilo sólo sortea entre las rotuladas**; quien
  reparte entre todas las direcciones es `build_identity_system`. Es una
  asimetría heredada y está anotada donde importa.
- **La fuente de contornos no tiene alfabetos no latinos**, así que un nombre en
  japonés, coreano, ruso o árabe cae a texto del sistema y el rótulo en arco del
  parche se cambia por uno recto.
- **Sólo el halcón y el toro tienen vista de perfil.** El jaguar, el elefante y
  el resto siguen siendo frontales; cada vista nueva es dibujo paramétrico
  aparte.

## Alternativas descartadas

- **Subir un poco el peso de las rotuladas y dejarlas como estaban.** Habría
  cambiado el reparto sin arreglar el fondo: cinco recetas repartidas entre más
  clubes siguen siendo cinco recetas.
- **Mantener el criterio de 65 % heráldico.** Era el requisito el que impedía la
  variedad; cambiarlo es la decisión, y por eso está escrita aquí y en la propia
  prueba.
