# ADR 0022 — La paleta de un club: dos, tres y tres

- **Fecha:** 1 de noviembre de 2026
- **Estado:** aceptado e implementado
- **Contexto:** petición del usuario: «hay que asignarle a los equipos, igual,
  su paleta de colores, algo identitario, que combine bien, deben de ser dos
  colores principales, 3 secundarios, y otros 3 terciarios, para que tengan
  margen de diseñar sus logos»
- **Se apoya en:** ADR 0015 (identidad generativa) y ADR 0019 (variedad de
  marcas)

## Problema

El compositor de marcas tenía la paleta escrita a mano:

```python
hue = rng.choice((0.68, 0.07, 0.43, 0.76, 0.96)) + rng.uniform(-0.02, 0.02)
field = oklch(rng.uniform(0.24, 0.32), rng.uniform(0.045, 0.09), hue)
palette = Palette(field=field, mark="#F4EAD5", ink="#101923", paper="#FFF9EE", accent=…)
```

Cinco tonos posibles para el campo, y **tres colores constantes** para todos
los clubes del mundo: el mismo crema, la misma tinta, el mismo papel. Tres de
cada cuatro colores de una identidad no eran de esa identidad.

Y eran cinco papeles. Un escudo que quiere dividir el campo, perfilar una
figura y rematar con un filete no tiene con qué: el blasón se fabricaba sus
tinturas derivando el campo en OKLCH —un paso más claro, un paso más oscuro—,
que es lo que se hace cuando no hay paleta.

## Decisiones

### D1 — Ocho papeles, agrupados como se usan

| Grupo | Papeles | Para qué |
| --- | --- | --- |
| **Principales (2)** | `field`, `mark` | los dos colores con los que se reconoce al club |
| **Secundarios (3)** | `accent`, `shade`, `tint` | realce, segundo tono de la base y tercer tono |
| **Terciarios (3)** | `ink`, `paper`, `metal` | perfilar, recortar y rematar |

`metal` es nuevo y tiene nombre: oro, plata, bronce, cobre o peltre. El filete
de metal dentro de la bordura es oficio heráldico, no un adorno.

### D2 — La armonía se declara, no se sortea color a color

`club_palette` elige primero un **esquema** —monocroma, análoga,
complementaria, complementaria dividida o tríada— y de él salen los tres tonos
(base, principal y tercero). La personalidad institucional inclina la elección:
arraigo local hacia la armonía, ambición hacia el choque del complementario o
el reparto de la tríada. Todo lo demás se deriva de esos tres tonos, así que
una paleta no es «ocho colores al azar» sino ocho colores que vienen del mismo
sitio.

El color principal se sortea entre dos familias: **pálido** —el crema de las
marcas clásicas— y **vivo**. Que fuera siempre crema era precisamente el
defecto.

### D3 — Dos cosas se imponen: el contraste y la distinción

- **Contraste WCAG** en lo que acaba pegado: principal y realce sobre la base
  a 4,5:1; tercer tono y metal sobre la base a 3:1; tinta y segundo de base
  sobre el principal a 3:1. Medido sobre 400 paletas: 0 incumplimientos.
- **Distinción perceptual**, que es otra cosa: dos tonos distintos con la misma
  claridad tienen contraste 1:1 y se ven perfectamente distintos, así que la
  separación se mide en **OKLab** (`MIN_ROLE_DISTANCE = 0.11`). Cada papel se
  aparta de los ya puestos moviendo **solo su claridad**, y dentro de la banda
  en la que sigue sirviendo para lo suyo.

Tres parejas tienden a juntarse y se separan a propósito: realce con principal
(en monocroma salen del mismo tono), segundo de base con tinta (las dos
oscuras) y tercer tono con metal (los dos medios). Si el metal choca, se prueban
los otros cuatro antes de moverlo: es lo que haría quien diseña.

El segundo de base baja cuando hay sitio entre la base y la tinta, y **sube**
cuando la base ya es oscura: «más oscuro que la base» y «más claro que la
tinta» no caben a la vez, y un segundo negro no separa nada.

Papel y tinta quedan fuera del reparto de distinción: el casi blanco y el casi
negro son estructura, y nadie espera que una crema y un blanco roto sean dos
colores distintos.

### D4 — La paleta es del club, no del dibujo

`build_identity_system` la compone **una vez**, con su propia subsemilla
(`derive_seed(identity_seed, "palette")`), y se la pasa a las siete candidatas
de escudo. Si cada candidata sorteara la suya, la identidad del club dependería
de cuál de los siete dibujos acabara ganando.

Queda guardada en el perfil (`IdentityProfile.palette`), agrupada y con el
oficio de cada color escrito, y la ficha del club la enseña: ocho muestras con
su nombre, su hexadecimal y para qué sirve.

### D5 — El blasón usa los colores del club

`tinctures()` ya no deriva dos tonos del campo con aritmética: ofrece el tercer
tono, el segundo de base, el realce, el metal, el papel y la tinta —los colores
del club, con su contraste ya hecho—. `charge_color()` suma el metal y el
tercer tono a sus candidatos, y la bordura interior se dibuja con el filete de
metal en el 45 % de los escudos.

Eso es el «margen para diseñar» que pedía el encargo: el escudo se divide,
perfila y remata sin salirse de la familia del club.

### D6 — Una marca guardada con cinco colores sigue siendo válida

`Palette` rellena los tres papeles nuevos al leerse, derivándolos del campo con
**la misma aritmética** que el blasón usaba antes de que existieran, y el metal
cae en un oro sobrio. Ninguna capa vieja los nombra, así que ningún escudo
anterior cambia de aspecto ni deja de dibujarse.

## Consecuencias

- Medido sobre 200 clubes: 200 bases distintas y 200 colores principales
  distintos, donde antes había cinco tonos y un crema.
- El `ColorRef` del contrato admite tres papeles más, y el esquema publicado
  (`docs/logo-schema.json`) se regeneró.
- Las decisiones de dibujo que venían después de la paleta se desplazaron en
  el flujo de números aleatorios, así que los escudos concretos de un club ya
  generado cambian. Los clubes guardados no: su marca está persistida.

## Alternativas descartadas

- **Medir la distinción con el contraste WCAG.** Sólo mira la luminancia: dos
  colores opuestos con la misma claridad le parecen el mismo color.
- **Ocho colores sorteados sueltos.** Pasan el contraste y no son una paleta.
- **Guardar la paleta aparte del perfil de identidad.** El color es parte de
  la identidad; separarlos permite que digan cosas distintas.
