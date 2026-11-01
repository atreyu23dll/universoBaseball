# ADR 0018 — Símbolos paramétricos y arquetipos de marca

- **Fecha:** 31 de octubre de 2026
- **Estado:** aceptado e implementado
- **Contexto:** petición del usuario después de mirar la galería del ADR 0017:
  «hay que trabajar con los símbolos, hacerlos más variados y flexibles, mucho
  trabajo de dibujo paramétrico. Además, en la vida real no sólo hay escudos y
  símbolos: hay símbolos sin escudo, escudos con 3 o 4 diseños y elementos
  alrededor»
- **Se apoya en:** ADR 0015 (contrato del logo y coherencia semántica) y
  ADR 0017 (silueta procedural y blasón por capas)

## Problema

El ADR 0017 arregló el escudo y dejó el contenido a medias. Mirando el catálogo
entero —cada símbolo con siete semillas en una rejilla— saltaban dos cosas:

1. **Quince de los veintidós símbolos eran el mismo dibujo.** `bird`, `bull`,
   `elephant`, `cactus`, `pine`, `oak`, `wheat`, `bridge`, `comet`,
   `constellation`, `ball`, `bolt`, `flame`, `moon` y `river` tenían uno o dos
   números interpolados en una ruta escrita a mano: cambiaba una anchura, no el
   dibujo. Cuatro clubes de una misma galería llevaban la misma torre.
2. **Ocho motivos del catálogo semántico no se podían dibujar.** `crown`,
   `star`, `wave`, `jaguar`, `shield_boss`, `home_plate`, `glove` y
   `crossed_bats` estaban en el mapa de familias pero no tenían generador, y se
   sustituían por un pariente (`crown` → `tower`).
3. **Sólo había una clase de marca.** Todo era un escudo con una figura dentro,
   cuando en la realidad conviven la marca sin escudo, el parche de gorra, el
   banderín, el escudo cuartelado con varias armas y el escudo acompañado de
   tenantes y cimera.

## Decisiones

### D1 — Cada símbolo se construye por su anatomía

Los quince se reescribieron con los parámetros que de verdad distinguen un
dibujo de otro:

| Símbolo | Lo que ahora varía |
| --- | --- |
| `ball` | comba de la costura, número de puntadas, una costura o dos, giro |
| `bolt` | los siete vértices del rayo: arranque, codos, muescas y punta |
| `flame` | de una a tres lenguas con su reparto, altura y gancho |
| `moon` | fase, giro, y la estrella que la acompaña o no |
| `river` | meandros, amplitud, ancho que crece, orillas |
| `cactus` | **dos especies**: saguaro con sus brazos y nopal de pencas |
| `pine` | pisos, vuelo, recogida y borde liso o en sierra |
| `oak` | lóbulos de la copa, ramas, raíces y bellotas |
| `wheat` | de una a tres espigas, granos, aristas y hoja |
| `constellation` | el trazado entero: cuántas estrellas y por dónde van |
| `bird` | envergadura, plumas, alzado, cola y hacia dónde mira |
| `bull` | el cuerno sobre una curva de tres puntos, orejas, hocico |
| `elephant` | abertura y caída de las orejas, trompa, colmillos |
| `bridge` | ojos de arco o **puente colgante** con torres y cables |
| `comet` | dirección, largo de la cabellera, mechones, puntas del núcleo |

Medido: **los treinta símbolos dan 24 dibujos distintos de 24 semillas**.

Tres piezas de geometría compartida hacen posible el resto: `_ribbon` (banda de
ancho variable a lo largo de una polilínea, que dibuja ríos, cuernos, trompas y
colas), `_oval` (elipse girada y muestreada) y `_bounds` (caja envolvente de una
ruta, que **rechaza los arcos** porque en `A rx ry giro bandera bandera x y` la
mitad de los números no son coordenadas).

**Dos lecciones que costaron un intento cada una.** La luna no se dibuja como
«círculo con un círculo dentro»: lo que sobresale del interior se rellena igual
y salen dos círculos solapados, así que se traza como **dos arcos entre las
puntas**, que son la intersección de las dos circunferencias. Y dos pencas de
nopal con el contorno del color del relleno se funden en una sola mancha: lo que
las separa es un contorno oscuro, no la geometría.

### D2 — El catálogo dibuja lo que el mapa semántico promete

Los ocho motivos huérfanos tienen generador propio, así que el catálogo pasa de
22 a **30 símbolos** y `DRAWABLE_FALLBACK` se queda **vacío**: el escudo ya no
tiene que conformarse con un pariente. La función se queda, porque añadir un
motivo al mapa antes que su contorno vuelve a ser posible y entonces basta una
línea para que nada se rompa.

### D3 — El lienzo manda, en un solo sitio

Catorce de los treinta se salían de la caja de 0 a 100 en su peor caso —un
cuerno largo, una arista de trigo—, y sólo se notaba cuando una variante
dibujaba el símbolo casi a tamaño completo. En vez de ajustar catorce
generadores a mano, `generate_symbol` **mide y encaja**: normaliza cada símbolo
para que llene el lienzo con un margen, lo centra y lo devuelve.

Dos cosas se ganan de una vez: ninguna figura se sale, y «escala 0,6» significa
lo mismo para una espiga estrecha que para una ola ancha —antes una figura
alargada se veía pequeña en mitad de un escudo vacío—.

### D4 — Tres arquetipos de escudo, no uno

- **simple**: una figura principal y sus muebles menores (lo del ADR 0017).
- **cuartelado**: el campo se parte en dos, tres o cuatro cuarteles y **cada uno
  lleva una figura distinta**, como cuando una casa reúne varias armas. Los
  cuarteles se miden sobre la silueta real, así que en un escudo de punta el de
  abajo es más estrecho, y cada figura se encoge hasta caber en el suyo.
- **acompañado**: escudo más pequeño con **tenantes** a los flancos, **cimera**
  sobre su burelete y **compartimento** debajo. La holgura del tenante se
  calcula contra el escudo y contra el lienzo a la vez; si entre los dos no cabe
  una figura que se vea, el escudo se queda sin tenantes en vez de llevarlos
  montados en el flanco.

Sobre 200 escudos: 119 simples, 48 cuartelados, 33 acompañados, y **200
estructuras gráficas distintas**.

### D5 — Y marcas que no son escudos

El estilo simbólico reparte entre cinco arquetipos: **escudo**, **disco o
rombo**, **marca libre** (la figura con su rótulo, sin soporte), **parche**
(disco con aro y el nombre en arco, como el de una gorra) y **banderín**
(bandera con asta, punta y rótulo). Sobre 200: 57 libres, 56 con escudo, 39
parches, 28 discos y 20 banderines.

### D6 — El rótulo de fuera va perfilado

Un nombre **fuera** del escudo se dibuja sobre lo que haya detrás —la página,
clara u oscura—, y con el color del club sobre un fondo del color del club no se
lee. Los rótulos exteriores llevan perfil de `paper`, que es lo que hace legible
un wordmark deportivo sobre cualquier fondo.

## Consecuencias

**Lo que se gana.** 30 símbolos con anatomía propia, ocho arquetipos de
composición entre escudo y marca, y un catálogo que no necesita sustitutos.
Ninguna figura se sale del lienzo, comprobado generador a generador.

**Lo que cuesta.** `symbols.py` pasa de 739 a unas 1.500 líneas: es dibujo
paramétrico, y el dibujo ocupa. La normalización añade un nodo de grupo por
símbolo, que el renderizador resuelve con una matriz más.

**Límites declarados.**

- **El `jaguar` se lee como felino, no como jaguar.** A este nivel de
  abstracción —silueta plana, sin texturas— un felino de frente es un felino;
  lo que lo distingue son las manchas, y están.
- **La rotulación sigue sin alfabetos no latinos**: un nombre en japonés,
  coreano, ruso o árabe cae en texto del sistema, como antes.
- **El parche usa la fuente de contornos «engraved»**, así que si el nombre
  lleva signos que no tiene, el rótulo en arco se cambia por uno recto.

## Alternativas descartadas

- **Ajustar a mano los catorce símbolos que se salían.** Es una lista de
  excepciones que se desactualiza en cuanto alguien añade el trigésimo primero.
- **Un catálogo de SVG dibujados fuera.** Rompe la variación por semilla, que es
  justo lo que se estaba arreglando.
- **Dejar `DRAWABLE_FALLBACK` como estaba.** Funcionaba, pero significa que el
  nombre promete una corona y el escudo dibuja una torre; con treinta
  generadores ya no hace falta mentir.
