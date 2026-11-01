# ADR 0015 — Identidad generativa: nombre y logo por capas

- **Fecha:** 26 de octubre de 2026
- **Estado:** aceptado e implementado
- **Contexto:** plantilla de identidad gráfica definida por el usuario
- **Se apoya en:** ADR 0003 (RNG derivado por contexto), ADR 0012 (R5: un
  contrato, una fuente) y ADR 0014 (organigrama: de ahí sale la personalidad de
  quien dirige el club)

## Problema

La identidad de un club se generaba, pero no se sostenía. Medido, no supuesto:

1. **El 59 % de los escudos no se leía.** Sobre 600 marcas generadas, el
   contraste WCAG entre el fondo del escudo y el símbolo que se pinta encima
   tenía mediana 2,2:1 y **mínimo 1,0:1** —literalmente invisible—. Entre el
   secundario y el acento, el 97 % quedaba por debajo de 3:1. La causa era
   generar en HSV: mover la «V» no mueve la luminancia que percibe el ojo.
2. **El logo decoraba la identidad en vez de construirla.** El motivo salía de
   `rng.choice` uniforme: un club llamado **Nopaleras** recibía un elefante 55
   veces de cada 600, y el cactus no existía en el catálogo.
3. **La gramática no podía expresar lo que se le pedía.** Las capas no tenían
   posición, escala, giro ni orden explícito, así que «un triángulo
   transparente **entre** el cuadrado y el elefante» o «**arriba**, tres rosas
   moradas» no eran descripciones representables. Y «las iniciales de la
   ciudad, como LA» daba `AD`, porque el monograma mezclaba lugar y apodo y
   descartaba el artículo.
4. **El contrato no se validaba y el único intérprete vivía en el frontend.**
   `layers` era `list[dict[str, Any]]`: un motivo mal escrito no fallaba, caía
   en el `else` del componente y **salía una estrella**. Nada podía exportar un
   PNG, un favicon ni probar un dibujo sin un navegador.

## Decisiones

### D1 — El color se genera en OKLCH y el contraste se exige

`simulation/identity/color.py` implementa OKLab/OKLCH (matrices de Ottosson, sin
dependencia nueva: son treinta líneas de álgebra) y el contraste de WCAG.

La paleta tiene **cinco papeles** —`field`, `mark`, `ink`, `accent`, `paper`—
con bandas de claridad fijas, y después se **repara**: `ensure_contrast` mueve
solo la `L`, conservando tono y croma, hasta que el símbolo alcanza 3:1 sobre su
fondo y el texto 4,5:1. Medido sobre 600 paletas nuevas: **0 por debajo del
umbral**, con desviación típica suficiente para que no sean todas iguales.

Lo que la personalidad de quien dirige el club mueve es el **tono y el croma**
—arriesgado acepta más intensidad, ambicioso busca el complementario—, nunca la
legibilidad.

### D2 — El contrato es un modelo validado, con colocación y orden

`LogoSpec` (Pydantic, unión discriminada por `kind`, `schema_version`) con tres
clases de capa: `shape`, `motif` y `text`. Cada una lleva:

- **colocación**: ancla, desplazamiento, escala y giro;
- **orden explícito** (`z`), que es lo que permite meter una capa entre otras
  dos sin reordenar nada;
- **nivel de detalle** (`min_size`): los píxeles mínimos a los que vale la pena
  dibujarla.

Un motivo inexistente ahora falla al generarse. El esquema se publica en
`docs/logo-schema.json` y una prueba falla si se queda obsoleto.

### D3 — Un solo intérprete, en Python, que emite SVG

`simulation/identity/render.py` es el único sitio que sabe dibujar un logo, y el
motor lo sirve en `GET /api/v1/clubs/{id}/crest.svg?size=N` con `ETag` y
`Cache-Control`. El componente del frontend dejó de dibujar: pide una imagen.

`size` no solo escala, **decide qué se dibuja**: a 28 píxeles el nombre completo
de un club mide 3 px y es una mancha, así que no se dibuja. Esa es la razón de
que el tamaño viaje al servidor.

Lo que se gana: export, favicon, imagen para compartir, pruebas de dibujo sin
navegador, caché por contenido, y la imposibilidad de que dos implementaciones
se separen.

### D4 — Motivos paramétricos, no dibujos

30 motivos, cada uno una **función** que recibe parámetros y devuelve primitivas
geométricas en una caja normalizada de 0 a 1. Una rosa de cinco pétalos y otra
de ocho son el mismo motivo con otro parámetro; el «elefante geométrico» es
composición de polígonos. El estilo es plano a propósito: lo que sobrevive a 28
píxeles es la silueta.

### D5 — El nombre y el símbolo hablan de lo mismo

`club_name` ya elegía una **familia semántica** —`community`, `ambition`,
`bold`, `steadfast`, `cosmic`, `nature`— a partir de la personalidad
institucional, y la tiraba. Ahora la devuelve (`ClubName.family`) y el logo la
usa: un club «nature» lleva cactus, pinos, olas o cumbres; uno «bold», llamas,
rayos o toros. Queda un 18 % de motivos del propio deporte —pelota, bates,
home— porque un club de béisbol puede llevar una pelota aunque se llame Cometas.

### D6 — Las marcas anteriores se traducen, no se reescriben

`simulation/identity/legacy.py` convierte las marcas de las dos generaciones
anteriores —dos colores y un `crest_shape`, o capas con `slot` y motivos en
español— en una especificación dibujable, **reparándoles el contraste**. No se
toca ni una fila: el pasado no se sobrescribe, y los 24 clubes que ya existían
siguen teniendo escudo.

### D7 — El perfil institucional precede a la marca

`IdentityProfile` persiste la semilla derivada, versión del generador, tipo de
institución, contexto de fundación ficticio, valores, decisión nominal y
lenguaje visual. Las referencias llevan estado: `verified`,
`documented_institution`, `generated` o `unavailable`. La ausencia de una
referencia cultural curada se guarda como ausencia; nunca se sustituye por un
hecho inventado sobre una población real.

Las universidades conservan el nombre documentado de la institución. Su perfil
declara expresamente que la identidad deportiva generada es ficticia y no una
marca oficial.

### D8 — Los nombres compiten como candidatas

El generador verbal crea hasta 18 candidatas mediante gramáticas territoriales,
relacionales, institucionales y simbólicas; compone raíces y modificadores,
evalúa longitud, repetición, naturalidad y ajuste institucional, y descarta las
demasiado parecidas a otra marca del universo. La candidata elegida conserva
nombre oficial, corto, siglas, apodo opcional, gramática, concepto y
justificación. Para un locale sin gramática curada se usa sólo el topónimo.

### D9 — La composición es un árbol y produce un sistema

`CompositionNode` añade grupos, capas, máscaras, repeticiones y ornamentos a
las hojas `shape`, `motif` y `text`. El SVG sigue siendo una salida: lo
persistido es el árbol. De un perfil salen siete variantes coordinadas:
principal, secundaria, monograma, símbolo reducido, gorra, fondo claro y fondo
oscuro. Cada una tiene URL y `ETag` propios.

`redesign_identity_system` es la única transición de revisión: exige un motivo
y una semilla nueva, incrementa la revisión y archiva el sistema anterior
completo. Desplegar una nueva versión del generador no la invoca.

Antes de persistir, siete candidatas principales se evalúan por contraste,
balance, legibilidad a 24 px, complejidad, límites del lienzo y coherencia
semántica. Un registro impide duplicados exactos y limita la repetición de una
misma estructura, aunque cambie el color.

## Alternativas descartadas

- **Seguir dibujando en el cliente.** Permite animación y theming por CSS, pero
  obliga a mantener dos intérpretes del mismo contrato, y el segundo siempre
  llega tarde. Si algún día hace falta, los tipos de TypeScript se generan del
  mismo modelo (`scripts/logo_schema.py --typescript`).
- **Una lista grande de nombres y de logos.** Es lo que el encargo descartaba:
  una lista se agota y no construye identidad.
- **Añadir `coloraide` o `cairosvg`.** La conversión de color son treinta líneas
  y el SVG se escribe como texto. El rasterizado a PNG queda pendiente y
  entonces sí convendrá una dependencia (`resvg` o `cairosvg`).
- **Validar el contraste solo con un aviso.** Un aviso que nadie lee produce
  escudos invisibles. Se repara el color o no se entrega.

## Consecuencias

- **Todos los escudos se leen.** Es la diferencia más visible: 0 de 600 por
  debajo del umbral, frente al 59 % anterior.
- **Cada variante es una URL cacheable**, y la ficha no interpreta el árbol:
  recibe las URLs, el perfil explicable y los resultados de calidad.
- **`make crest-sheet`** dibuja 120 identidades en una hoja de contactos para
  mirarlas juntas. Ninguna aserción sustituye a eso: cien escudos juntos
  enseñan en dos segundos si la paleta se repite o si los símbolos se parecen.
- **Lo que no está hecho:** rasterizado a PNG, favicon por club, imagen para
  compartir y variantes adicionales horizontal/monocroma. Las siete variantes
  SVG ya se generan y persisten.
- La identidad verbal sigue teniendo el límite que ya tenía: fuera de los diez
  idiomas con gramática declarada, un club se llama como su topónimo y nada más.
  No se inventan palabras en idiomas que el motor no conoce.
