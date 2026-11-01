# ADR 0017 — Escudos blasonados: silueta procedural y emblema por capas

- **Fecha:** 31 de octubre de 2026
- **Estado:** aceptado e implementado
- **Contexto:** petición del usuario tras mirar una tanda de escudos: «me gusta que
  tenga atrás la forma de escudo típico, pero parecen de videojuego con
  plantillas selectas; me gustaría que fuera con iconos creativos, únicos, que
  tengan varios elementos, y que los escudos de detrás sean más procedurales»
- **Se apoya en:** ADR 0015 (identidad generativa: color en OKLCH, contrato
  validado, un solo intérprete) y ADR 0016 (el nombre acuñado que el escudo
  tiene que acompañar)

## Problema

Mirando cien escudos juntos, lo que delataba la plantilla no era el color ni el
símbolo:

1. **Había una sola silueta.** `Shape.SHIELD` era **una ruta escrita a mano** en
   `render.py`, la misma para todos los clubes. El contorno es lo primero que ve
   el ojo, y era idéntico.
2. **Había cinco composiciones.** La rama heráldica sorteaba un `layout` entre
   `ribbon`, `chief`, `wreath`, `quartered` y `triple`. Cinco recetas fijas
   reparten cien escudos en cinco grupos reconocibles.
3. **El emblema era una figura sola.** Un símbolo grande en el centro y nada
   más: ni campo partido, ni pieza honorable, ni muebles menores. La partición
   que existía se pintaba al 22 % de opacidad y no se veía.
4. **La cinta y la corona eran dibujos fijos.** La misma cinta y el mismo laurel,
   trazo por trazo, en todos los escudos que los llevaban.
5. **Los símbolos apenas variaban.** `tower` sólo cambiaba de anchura: cuatro
   clubes de la misma galería llevaban la misma torre. `anvil` sólo cambiaba el
   cuerno —y su silueta se leía como un cáliz, no como un yunque—. `gear`
   cambiaba el número de dientes y nada más.

## Decisiones

### D1 — La silueta se construye, por familias

`simulation/identity/escutcheon.py` describe el **flanco derecho** con
parámetros de blasón —anchura de hombros, caída del jefe, curvatura del flanco,
forma de la punta— y lo refleja. Los parámetros no se sortean sueltos: van por
**familias** (inglés de punta, francés moderno, ibérico redondo, oval italiano,
de torneo, barroco de cintura, estandarte, ojival), porque sortear cada número
por separado produce calderos y bombillas en vez de escudos.

Dentro de la familia el azar es continuo: **500 semillas dan 500 siluetas
distintas**. La muesca de lanza del escudo de torneo se abre **después** de
reflejar, en un solo flanco, porque es asimétrica de verdad; dibujarla antes
daba escudos con cuernos. La bordura interior se vuelve a emitir desde los
mismos segmentos, no desde una forma parecida, o se ve la pestaña.

### D2 — El emblema tiene capas, como un blasón

`simulation/identity/blazon.py` aporta el vocabulario y `grammar.py` lo monta:

| Capa | Repertorio |
| --- | --- |
| Partición del campo | 13: partido, cortado, tronchado, tajado, cuartelado, gironado, fajado, palado, bandado, chapé, mantelado, ondado, ajedrezado |
| Pieza honorable | 10: jefe, faja, palo, banda, cheurón, cruz, sotuer, bordura, pila, campaña |
| Mueble principal | el símbolo semántico del nombre (ADR 0015, D5) |
| Muebles menores | 7 piezas geométricas —estrella, roel, anillete, losange, cruceta, flor de lis— o un **segundo símbolo de la misma familia semántica** |
| Escudete | cuando el fondo es claro o inquieto |
| Exterior | cinta construida, corona de ramas, fila de estrellas, año de fundación |

Cada capa se sortea por su cuenta, así que el espacio ya no son cinco recetas.
Los muebles menores se dibujan con `role="ornament"`: una estrella acompaña, no
afirma nada sobre el club, y por eso no entra en la comprobación de coherencia
semántica —que sigue exigiéndose al mueble principal—.

### D3 — La colocación se calcula, no se ajusta a ojo

`Escutcheon.width_at(y)` dice cuánto escudo hay a cada altura, porque en uno de
punta no cabe en la campaña lo que cabe en el jefe. Con eso:

- la figura principal se dimensiona por el ancho **y** por el alto disponibles
  —sólo por el ancho se salía por arriba en los escudos cuadrados—;
- ningún mueble menor se coloca a menos de `escala_principal × 50 + escala_menor
  × 46` del centro, que es la distancia a la que dejan de tocarse de verdad;
- lo que no cabe se cae: un escudo apretado se lee peor que uno con una figura
  menos;
- si hay cinta, nada se dibuja por debajo de ella.

### D4 — Un solo color fuerte por escudo

Toda tintura candidata se mide **contra el campo** (para que la partición se
vea, ≥1,7:1) y el color del mueble se elige **después** de saber sobre qué va a
ir, exigiendo el umbral gráfico de WCAG contra todos los fondos que pisa. Atar
las dos cosas a la vez dejaba una única tintura posible en cuanto la marca era
clara.

Encima de eso hay una regla de sobriedad: si la partición usa un color fuerte
—acento, papel o tinta—, la pieza honorable usa un derivado del campo. Dos
colores gritando a la vez convierten el escudo en una bandera.

### D5 — Los exteriores también se construyen

La cinta se arma con cuerpo, vuelo y colas, y varían su anchura, su comba, su
alto y el remate —escotada, recta o enrollada—. La corona varía el número de
hojas, la abertura de la rama, el tamaño de la hoja y la altura de arranque. El
año de fundación entra bajo el borde del jefe, y sólo si no pisa a la figura.

### D6 — Los símbolos más repetidos tienen anatomía

- **torre**: 2-4 almenas, altura, vuelo de la base, puerta en arco o recta, 0-3
  saeteras y torreta lateral que se funde con el cuerpo.
- **yunque**: redibujado. Manda la horizontal de la mesa y debajo el talle se
  estrecha antes de abrirse; la silueta anterior se cerraba hacia arriba y se
  leía como un cáliz.
- **engranaje**: profundidad del diente, flancos rectos o en trapecio, y cubo de
  disco, hexágono, radios o cuadro.
- **abstracto**: tres producciones nuevas que son **composiciones** —sello con
  anillo y polígono interior, rosa de los vientos con centro, arco sobre dos
  pilares con clave—, porque una marca abstracta de un solo trazo se lee como un
  logotipo genérico.

### D7 — El escudo se explica

El `rationale` del logo ya no dice «geometría parametrizada»: dice el blasón.
«Escudo ibérico: jefe recto, flanco recto, punta redonda; tronchado, jefe,
bordura, muebles 2-1.»

## Consecuencias

**Medido sobre las cien identidades de la galería de aceptación:** 100 de 100
tienen **estructura gráfica distinta** (`demo_manifest()["structures"]`); el
criterio de aceptación pedía 50. Las cien siguen pasando las comprobaciones de
contraste, encuadre y coherencia semántica que exigía el ADR 0015.

**Lo que no cambió, a propósito:** el contrato `LogoSpec` —las siluetas nuevas
son `PathLayer` con su caja declarada, no un tipo nuevo—, el único intérprete en
Python, el servicio con `ETag` y la retirada de capas por `min_size`. Un escudo
antiguo persistido se sigue dibujando igual.

**Límites declarados.**

- **Ocho motivos del catálogo siguen sin contorno** (`crown`, `star`, `wave`,
  `jaguar`, `shield_boss`, `home_plate`, `glove`, `crossed_bats`): se dibuja el
  pariente dibujable de la misma familia, declarado en `DRAWABLE_FALLBACK`.
- **El catálogo sigue siendo de 22 símbolos.** La variedad nueva viene de la
  composición y de la anatomía; dos clubes de la misma familia semántica pueden
  seguir llevando el mismo animal, con otro escudo alrededor.
- **La fuente de rotulación no tiene todos los alfabetos.** Un nombre en
  japonés, coreano, ruso o árabe cae en texto del sistema, como antes.

## Alternativas descartadas

- **Añadir más plantillas.** Es lo que ya había: pasar de cinco recetas a quince
  retrasa el problema una galería más.
- **Dibujar los escudos a mano y guardarlos como imágenes.** Rompe la
  reproducibilidad por semilla, el escalado y la retirada de detalle por tamaño,
  y multiplica por cien el peso de lo persistido.
- **Generar el escudo con un modelo de imagen.** No es reproducible, no cabe en
  el contrato validado y no se puede explicar por qué salió ese dibujo.
