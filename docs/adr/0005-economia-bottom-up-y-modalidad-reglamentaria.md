# ADR 0005 — Economía de abajo arriba y modalidad como reglamento

- **Fecha:** 22 de octubre de 2026
- **Estado:** aceptado e implementado
- **Contexto:** FIX V2 de Fase 1, fases P1 y P3
- **Reemplaza:** la parte del ADR 0002 y de `docs/architecture.md` que daba por
  buena una economía derivada del «nivel de la competición»

## Problema

La primera implementación tenía una cadena causal invertida:

```text
etiqueta del formulario  →  nivel de liga  →  presupuesto  →  talento
```

Consecuencias medidas antes del cambio, con el fixture de Ciudad Juárez:

| Etiqueta elegida | Mediana de presupuesto |
|---|---|
| `amateur` | 433 794 MXN |
| `contextual_auto` | **1 876 351 MXN** |
| `professional` | 3 553 002 MXN |

Una liga llanera de barrio con clubes de casi dos millones de pesos, y la
diferencia entre un caso y otro era un desplegable. El FIX V2 lo prohíbe
expresamente (§7.2: «está prohibido `if league.mode == "amateur": budget =
1_000_000` y cualquier variante de montos rígidos»), y además prohíbe preguntar
por riqueza, propiedad, personal o instalaciones (§1.3, §10.1).

## Decisión

### 1. La causalidad se invierte

```text
territorio + reglas de la competición
  → recursos locales finitos (patrocinio, socios, campos)
    → organización propia de cada club (gobierno, sede, ambición)
      → cuentas de abajo arriba: lo que recauda y lo que puede pagar
        → nivel efectivo de la competición, que emerge de todo lo anterior
          → talento que la competición atrae del mercado compartido
```

El código lo hace cumplir en el orden de `generate_competition_world`:
`generate_clubs` ya no recibe el pool de jugadores, y `CompetitionContext.level`
**lanza una excepción** si alguien lo pide antes de que
`resolve_effective_level` lo haya calculado. No es una convención: es un error
en tiempo de ejecución.

### 2. Un ancla monetaria por jurisdicción, y solo una

Los índices del perfil regional son relativos (0–1) y no pueden producir
importes por sí solos. Cada país del fixture declara ahora una
`EconomicAnchor`: moneda de curso legal y **gasto mensual de referencia de un
hogar**, estimado y con año. Es el único punto del simulador donde un índice se
convierte en dinero.

Dos consecuencias buscadas:

- Cualquier presupuesto se puede leer como «tantos meses de gasto doméstico»,
  que es una magnitud discutible y comparable entre países.
- Un territorio **sin ancla** no recibe cifras inventadas: sus importes salen
  `null` con confianza `insufficient_data`, como pide §7.2 y como muestra el
  ejemplo de respuesta de §10.2.

La moneda deja de ser un ajuste del universo (`MXN` por omisión, que era la
violación de §4.4) y pasa a ser un dato derivado del territorio.

### 3. La modalidad es reglamento, no plantilla

`participation_modality` —llanera, amateur organizada, escolar/formativa,
semiprofesional, profesional— es la **única** pregunta de naturaleza
institucional del asistente, y lo que determina es:

- si se admite compensación a los jugadores (`CompensationRule`, ajustable por
  el usuario en `financial_regulations`),
- si se espera licencia,
- cuántos partidos por semana considera sostenible el marco, que afecta al
  calendario y a los meses de actividad.

Lo que **no** determina: ni un importe, ni una forma de gobierno, ni una sede,
ni el talento de nadie. Hay una prueba que lo vigila
(`test_d02_la_modalidad_no_decide_el_patrimonio`): cambiar solo la etiqueta no
puede multiplicar por dos la mediana de presupuesto del mismo territorio.

### 4. Los recursos locales son finitos y disputados

`LocalResourcePool` da a cada mercado una bolsa publicitaria, una población
afiliable y un número de campos utilizables, **y los clubes de la zona se los
reparten** en proporción a su alcance comunitario. Plantar veinte clubes en un
barrio no multiplica el dinero: lo divide, y la escasez de campos empuja a
compartir sede.

### 5. El presupuesto es el gasto que se puede sostener

Cada club estima primero sus ingresos (cuotas, su parte del patrocinio local,
taquilla si controla el recinto, apoyo institucional según su gobierno,
derechos de emisión y merchandising **solo si tiene audiencia que los
justifique**) y después decide gastos: primero los obligatorios —campo,
arbitraje, transporte sobre distancias reales, material, uniformes,
administración, seguro y atención médica si el reglamento los exige—, y solo
con el margen los discrecionales. Si no cubre lo obligatorio, queda en déficit
y se dice; nadie le regala dinero para completar la liga.

Resultado con el mismo fixture, después del cambio:

| Escenario | Presupuestos | En meses de gasto doméstico |
|---|---|---|
| Llanera, Ciudad Juárez, 8 clubes | 73 000 – 199 000 MXN | 6 – 17 |
| Profesional, nacional, 8 clubes | 0,9 – 3,4 M MXN | 74 – 280 |

La diferencia ya no es una etiqueta: son mercados de 300 000 habitantes frente
a mercados de millones, con audiencia, patrocinio y viajes distintos.

## Consecuencias

- **`ContextualLevel` desaparece del contrato.** Con él se van
  `generation.professionalization`, `generation.economy` y
  `generation.institutional_maturity`. La API los rechaza con el código
  `DEPRECATED_CLUB_GENERATION_FIELD` en vez de aceptarlos y esconderlos.
- **El esquema de reglas sube a 2.0.0** y los reglamentos guardados se migran
  dejando constancia en `rules_json.migration_note` de qué se quitó y por qué.
  Las temporadas ya jugadas **no** se recalculan.
- **El aforo de un estadio ya no depende del nivel de liga** sino del acuerdo de
  sede, del mercado y del alcance del club. Deja de haber circularidad entre
  «tiene estadio porque es rico» y «es rico porque tiene estadio»: el recinto es
  causa de la taquilla, no consecuencia del presupuesto.
- **La movilidad entre categorías necesitaba otro factor.** `adapt_budget` ya no
  usa un factor de liga: convierte el nivel efectivo a meses de coste de
  referencia (`level_to_months`, la inversa exacta de
  `resolve_effective_level`) y compara las dos categorías. Sigue siendo una
  transición, no un recálculo.
- **La calidad de juego sigue necesitando un número.** El motor de partidos lo
  recibe del nivel efectivo guardado en la procedencia de la competición, que
  ahora significa «los recursos que sus clubes reunieron de verdad».

## Lo que esto no arregla

- **La escala profesional está por debajo de la realidad.** Un club de la Liga
  Mexicana de Béisbol maneja bastante más que los 1–3 M MXN que salen aquí,
  porque faltan ingresos que dominan ese nivel: derechos de televisión
  nacionales, traspasos, explotación comercial. Están declarados como ausentes
  —no hay ninguna partida que los finja— y entran en la Etapa 4.
- **Los coeficientes son heurísticas sin calibrar.** Lo que está garantizado es
  la trazabilidad de cada importe, no su exactitud. Ver
  `docs/simulation-calibration.md`.
- **El territorio sigue siendo un fixture local.** Mientras la fase P2 no
  implemente GeoNames + PostGIS + geoBoundaries, el ancla monetaria solo existe
  para los cinco países del fixture, y Kampala no se puede elegir.

## Alternativas descartadas

- **Preguntar al usuario por financiación, salarios, propiedad y personal**, que
  es lo que proponía la adenda V1. El propio FIX V2 lo descarta: convierte al
  usuario en administrador de cada club y uniforma las instituciones.
- **Dejar un multiplicador por modalidad «solo para empezar».** Es exactamente
  el defecto que había que quitar; con él, cualquier modelo posterior seguiría
  colgando de una etiqueta.
- **Inventar un precio en pesos para cada partida.** Sin ancla declarada, los
  importes serían falsa precisión. Con ancla, son una estimación con fuente,
  año y confianza, y sin ancla no hay importe.
