# ADR 0016 — Nombres acuñados: morfología por idioma y vetas de identidad

- **Fecha:** 31 de octubre de 2026
- **Estado:** aceptado e implementado
- **Contexto:** petición explícita del usuario: «que no se haga a partir de una
  lista, ya que muchos se repiten; no necesariamente tiene que crearse rápido,
  sino tomar su tiempo en desarrollar una identidad»
- **Se apoya en:** ADR 0003 (RNG derivado por contexto), ADR 0014 (organigrama:
  de ahí sale la personalidad institucional) y ADR 0015 (identidad generativa:
  el nombre y el símbolo tienen que hablar de lo mismo)

## Problema

El generador de nombres era un combinador de **nombres acabados**. Medido, no
supuesto, sobre 96 clubes en una misma región:

1. **El inventario eran 24 palabras por idioma** —seis familias semánticas por
   cuatro raíces—. «Viento» salió **siete veces**; «Sol», cuatro; «Unión»,
   «Fuego», «Raíces», «Guardianes», «Sierra» y «Río», tres cada una.
2. **La diferencia entre dos clubes era el prefijo.** «Club Viento», «Deportivo
   Viento» y «Viento del Norte» pasaban el control de duplicados porque
   `NameRegistry` comparaba la **cadena final**. Para una persona son la misma
   marca.
3. **El nombre no venía de ningún hecho del club.** Salía de la personalidad de
   quien lo dirige y de nada más: la altitud de la plaza, su franja climática,
   el año de fundación y quién sostiene al club no entraban en la decisión,
   aunque el motor ya los conocía todos.

## Decisiones

### D1 — El inventario son morfemas, no nombres

`simulation/generation/morphemes.py` guarda **raíces** con sus rasgos (género,
familia semántica, motivo gráfico, etiquetas ecológicas, de oficio y de época) y
**qué alomorfo** toma cada una en cada clase de sufijo. «Salineros» no está
escrito en ningún sitio: está `salina` y está que admite `agentivo`.

Raíces por idioma: **165 en español**, 60 en inglés y entre 42 y 65 en los ocho
idiomas curados. **673 en total**, frente a 24 por idioma antes.

Una prueba (`test_las_palabras_se_acunan_con_reglas_y_no_estan_escritas`) falla
si alguna de las dieciséis palabras de referencia aparece escrita como unidad en
el inventario. Es la que impide volver atrás sin darse cuenta.

### D2 — La morfología es real, y su profundidad es por idioma

`simulation/generation/morphology.py` implementa las reglas que el español
aplica de verdad al sufijar:

| Regla | Entrada | Salida |
| --- | --- | --- |
| /k/ se escribe `qu` ante *e, i* | `barranca` + `-ero` | barran**qu**ero |
| /θ/ se escribe `c` ante *e, i* | `cerveza` + `-ero` | cerve**c**ero |
| /g/ se escribe `gu` ante *e, i* | `vega` + `-ero` | ve**gu**ero |
| La tilde se va al desplazarse el acento | `médano` + `-ero` | m**e**danero |
| Cae la vocal final ante sufijo vocálico | `álamo` + `-eda` | alam**eda** |
| Tema irregular declarado | `roble` → `robled-` + `-al` | robledal |
| Plural con tilde que se pierde o se mantiene | `halcón`, `jabalí` | halcones, jabalíes |

El alomorfo **se declara por raíz** porque en español la elección es léxica y no
se puede deducir: `pino` → pin**ar**, `arena` → arena**l**. Un tema escrito a
mano (`tranvi|ario`) es definitivo: aplicarle la caída de vocal daría
*tranvaria*.

La concordancia es una regla, no una coincidencia: las plantillas declaran si
piden sustantivo o adjetivo y en qué género, así que de `salina` sale «Unión
Salinera» y «Deportivo Salinero», y el apodo de un gremio va en masculino plural
—«los Molineros»—, nunca en femenino.

**Hasta dónde llega cada idioma**, declarado y no disimulado: español e inglés
derivan; portugués, japonés, alemán, francés, coreano, ruso, árabe y lingala
tienen inventario curado y ampliado que se usa **tal cual**; un país sin
gramática curada sigue recibiendo su topónimo verificado y nada más. El motor no
fabrica morfología de un idioma que no sabe conjugar.

En inglés la pieza productiva es la composición —«Salt Hawks», «Timber
Millers»—, que es como se nombra de verdad en ese idioma: 897 compuestos con 60
raíces.

### D3 — Toda palabra acuñada pasa un filtro

`plausibility` silabea con **ataque máximo** («es-tre-lla», no *est-re-lla*),
comprueba que cada ataque y cada coda existan en el idioma, descarta la sílaba
repetida que a veces deja el empalme, acota la longitud y veta un puñado corto y
explícito de secuencias malsonantes. Lo que no pasa, no sale.

### D4 — Tres vetas de identidad, una por club

Un nombre es la huella de algo que ya le pasó al club, así que antes de acuñar
una palabra se decide **por qué** se va a llamar así:

- **territorio** — la altitud, la franja climática que implica la latitud y el
  tamaño de la plaza. Una plaza árida da Huizachales, Médanos o Cardones; una
  tropical, Cañeros o Ceibales.
- **época** — el año de fundación. Las sociedades de antes de 1940 se nombraban
  por lo que decían defender (Porvenir, Fraternidad, Alianza); la marca de 1995
  en adelante prefiere una palabra sola y corta.
- **patronazgo** — quién lo sostiene. Una casa familiar o una empresa pone su
  apellido delante y su gremio detrás: «Deportivo Guajardo, los Tipógrafos».

La veta **restringe el vocabulario y la gramática**; no es una etiqueta añadida
después. Se sortea con los pesos que da el club: una empresa deportiva enseña a
su patrón mucho más que un colectivo vecinal, y un club viejo se nombra por sus
valores más que uno de 2019.

**Degradan en vez de fallar**: sin geografía, la veta territorial usa el
repertorio natural completo; sin año de fundación, la de época pierde el
registro pero no el vocabulario; sin repertorio de apellidos en ese idioma, la
de patronazgo no está disponible y el peso se reparte.

### D5 — La presión es sobre la raíz y la plantilla, no sobre la cadena

`NameRegistry` cuenta las **raíces** y las **plantillas** gastadas en el
universo y las encarece. No las prohíbe: un universo grande agota el inventario
y entonces repetir es lo correcto. Medido ahora: 24 clubes en una misma plaza
usan 24 raíces distintas, y en 96 clubes ninguna raíz pasa de tres usos.

### D6 — El nombre guarda de dónde salió

`ClubName` y `NamingProfile` conservan la veta (`motivation`), el hecho que la
motivó (`story`), la acuñación (`formation`: «mezquite + -al») y la raíz
(`root`). El escudo usa el **motivo declarado por la raíz**, que acierta con una
palabra acuñada —«Nopalera» → cactus— sin tener que reconocer su ortografía, y
cualquier motivo que no pertenezca a la familia del nombre se descarta: «Caminante
del Río» no puede llevar un río sólo porque el modificador lo mencione.

## Consecuencias

**Lo que se gana.** Por plaza hay **11.301 denominaciones** alcanzables en
español sin contar apellidos, y 873.276 contándolos. La repetición percibida
—misma palabra con otro prefijo— desaparece mientras quede inventario, y el
nombre se puede explicar: la ficha del club guarda por qué se llama así.

**Lo que cuesta.** Generar un nombre ya no es sortear un elemento: se eligen
veta y seis raíces semilla, se acuñan sus palabras, se cruzan con las plantillas
que la veta y la época habilitan, se filtra y se puntúa. Son **5,7 ms por club**
(0,57 s por cada cien), y hubo que indexar el registro por prefijo de palabra
para que comparar candidatas contra el universo no fuera cuadrático: sin eso
costaba 0,6 s por club.

**El año de fundación pasó a su propio cauce RNG.** La veta de época lo necesita
**antes** del nombre, y moverlo dentro del cauce compartido habría desplazado
políticas y reputación de todos los clubes. Se sortea desde
`derive_seed(identity_seed, "foundation")` y el sorteo histórico se sigue
consumiendo en su sitio: ni las cuentas ni los recintos cambian.

**Límites declarados.**

- **El clima se estima por latitud.** El motor no tiene precipitación ni
  distancia a la costa. La franja árida subtropical (20°–35°) es un patrón real
  pero grueso, y el relato del club lo dice: «estimada por latitud».
- **Los nombres de persona siguen siendo de español de México.** Esto cambia la
  marca del club, no los antropónimos; el repertorio de apellidos de la veta de
  patronazgo existe en español, portugués e inglés.
- **Ocho motivos del catálogo no tienen contorno** (`crown`, `star`, `wave`,
  `jaguar`, `shield_boss`, `home_plate`, `glove`, `crossed_bats`). Mientras no
  lo tengan se dibuja el pariente más cercano de la **misma familia**
  (`crown` → `tower`, `jaguar` → `bull`), declarado en `DRAWABLE_FALLBACK`.
- **La distribución de años de fundación es la de antes** —gaussiana de 22 años
  sobre la fecha del mundo—, así que el 95 % de los clubes son posteriores a
  1980 y el registro mutualista casi no se ve. Ensancharla es otra decisión, de
  historia y no de nombres.

## Alternativas descartadas

- **Ampliar la lista de apodos.** Multiplica el inventario por una constante y
  deja el problema intacto: el espacio sigue cerrado y la repetición vuelve con
  la siguiente liga grande.
- **Pedir los nombres a un modelo de lenguaje.** Rompe la reproducibilidad por
  semilla, que es el contrato del motor (ADR 0003), mete una dependencia de red
  en la generación de un universo y no se puede explicar por qué salió un
  nombre.
- **Componer sílabas al azar.** Da palabras sin significado, y entonces el logo
  no puede hablar de lo mismo que el nombre (ADR 0015, D5). La derivación con
  alomorfo declarado conserva la raíz y, con ella, el símbolo.
