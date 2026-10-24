# ADR 0007 — Liquidación de temporada y vida institucional

- **Fecha:** 23 de octubre de 2026
- **Estado:** aceptado e implementado
- **Contexto:** FIX V2 de Fase 1, fase P5 (§6.3, §7.1, §11.2)
- **Se apoya en:** ADR 0005 (economía de abajo arriba) y ADR 0004 (frontera de
  temporada)

## Problema

Después de P3 las cuentas de un club eran correctas y trazables, pero
**estáticas**. Un club generado en 2042 tenía en 2051 el mismo presupuesto, la
misma afición, la misma sede y la misma forma de gobierno. El presupuesto era
una *previsión* que nunca se contrastaba con nada, así que:

- Un patrocinio previsto equivalía a dinero en caja. Nadie incumplía nunca.
- Una temporada con partidos suspendidos recaudaba la misma taquilla que una
  completa.
- Un club con las cuentas imposibles seguía inscribiéndose cada año. La liga no
  perdía nunca a nadie, y por tanto tampoco ganaba nada: no había historia.

El FIX V2 lo nombra en §6.3 —«en años posteriores la distribución podría
cambiar: patrocinadores que llegan o se retiran, adquisiciones o votaciones,
instalaciones nuevas, disminución de afiliados, fusiones, crecimiento o
desaparición»— y en §7.1 pide expresamente **no confundir un patrocinio
prometido con dinero cobrado**.

## Decisión

Separar **prever** de **cobrar**, y hacer que la institución cambie como
consecuencia de lo segundo.

### 1. Dos módulos puros, en `simulation/economy`

| Módulo | Pregunta que responde |
|---|---|
| `club_finances.py` (P3) | ¿Qué puede recaudar y gastar este club esta temporada? |
| `season_close.py` (P5) | ¿Qué cobró y qué pagó **de verdad**? |
| `evolution.py` (P5) | ¿En qué se ha convertido para el año que viene? |

`close_season()` recibe el perfil previsto, la caja, la deuda y **los partidos
jugados en casa frente a los programados**, y devuelve un `SeasonLedger`: un
asiento por partida, cada uno con su importe real, el previsto al lado y el
motivo del desfase en lenguaje natural («se jugaron 5 de 10 partidos en casa, y
se cobró el 45 % de la taquilla prevista»).

Reglas que el modelo impone, no sugiere:

- **Lo obligatorio se paga entero.** Si no hay caja, se paga con deuda. No se
  perdona una obligación para que cuadre el balance.
- **Lo discrecional se recorta** (85–100 % de lo previsto).
- **Lo que no se pudo cubrir pasa a deuda**, con un 12 % de interés anual y una
  amortización del 25 % de la caja disponible cuando el año va bien.
- **Sin ancla monetaria no hay liquidación.** La temporada se cierra sin
  asientos y las cuentas siguen sin cuantificar, con su nota. No se inventa un
  cero.

### 2. Desaparición tras una racha, no tras un tropiezo

Un club queda `insolvent` cuando su deuda supera año y medio de obligaciones.
**Dos temporadas consecutivas** así y deja de competir
(`SEASONS_INSOLVENT_TO_FOLD = 2`). Una mala temporada no cierra un club; una
racha sí.

Lo que **no** se hace, y es la decisión de fondo: no se le inyecta dinero para
mantener el número de equipos de la liga. La competición se queda con los
clubes que puede sostener su territorio, y si se queda con menos de dos, se
desactiva y se dice por qué. Esto es la misma regla del ADR 0005 llevada al
tiempo: el entorno manda, y la etiqueta de la competición no rescata a nadie.

Un club que desaparece **conserva su fila**, su historia, sus títulos y sus
libros. Deja de competir; no se borra. Y deja de contar para ascensos y
descensos: `branch_state()` lo excluye, así que su plaza queda vacante en vez de
mover a un fantasma.

### 3. Evolución con causas, no con saltos

`evolve_club()` devuelve un `Evolution` con multiplicadores y cambios
explicados:

- **Base social**: se mueve por el porcentaje de victorias, y de forma
  asimétrica (+0,10 por punto de rendimiento al ganar, −0,06 al perder), más
  ruido normal. La gente se engancha antes de lo que se va.
- **Alcance en la zona**: sube con una temporada sana y proporcionalmente a la
  ambición; baja cuando las cuentas están en rojo, lo que encarece la temporada
  siguiente. Es el mecanismo que hace que una mala racha se note.
- **Sede**: mejora (itinerante → público compartido → alquilado → propio) si
  cerró con más de 24 meses de gasto en caja y la ambición lo empuja; se
  degrada si no puede sostenerla.
- **Gobierno**: se **formaliza** —colectivo → asamblea de socios → fundación;
  familiar o con respaldo empresarial → sociedad deportiva— cuando hay al menos
  ocho años de historia, arraigo y cuentas sanas. No existe el camino inverso
  por capricho: una franquicia no se vuelve un grupo de amigos.

### 4. Dónde encaja, y en qué orden

`club_evolution_service.close_edition_finances()` se llama desde
`season_service.process_season_boundaries()`, **antes** del intercambio de
clubes y antes de abrir la temporada siguiente, dentro de la misma transacción
del día. El orden importa: un club que cierra no asciende, y una plaza de
ascenso no puede adjudicarse a quien ya no existe.

### 5. Volver a presupuestar, con el mismo código

Evolucionar la afición y el alcance no serviría de nada si el presupuesto
siguiera siendo el del año de fundación. Al cerrar la edición, una **segunda
pasada** vuelve a presupuestar la temporada siguiente de los clubes vivos
(`simulation/generation/season_forecast.py`), llamando a la **misma**
`estimate_club_finances()` que usó la generación. No hay un segundo modelo
económico que pueda divergir del primero.

Lo que cambia entre una llamada y otra es solo lo que el mundo cambió: la base
social de cada club, su alcance comunitario, su gobierno, su sede y **cuántos
clubes se reparten los recursos de la zona**. Esa última parte es la que
mantiene la regla del ADR 0005: la bolsa publicitaria y la población afiliable
de un territorio se recalculan desde el territorio, no desde los clubes, así que
**no crecen porque un club crezca**. Un club que se fortalece le quita parte a
sus vecinos, y cuando uno desaparece su parte se reparte entre los que siguen.

La pasada es la segunda y no la primera por la misma razón que en la generación:
el reparto necesita conocer a todos los supervivientes antes de dividir.

### 6. Persistencia: dos tablas que no se sobrescriben

- `club_season_ledgers`, con clave única `(club_id, season)`. Esa clave **es** el
  mecanismo de idempotencia: reintentar un avance no liquida dos veces la misma
  temporada ni mueve un peso. Es el mismo patrón que `season_transitions` del
  ADR 0004.
- `club_organization_changes`: un registro por cambio, con `before`, `after` y
  `reason`. La historia institucional se lee, no se deduce.

## Alternativas descartadas

- **Liquidar al vuelo, partido a partido.** Más realista en apariencia, pero
  obligaría a escribir en las cuentas del club en cada simulación de partido y
  convertiría cualquier reintento en un problema de idempotencia por partido.
  El cierre anual es una frontera limpia y auditable.
- **Un balance que siempre cuadra.** Es lo que hacía el modelo anterior de
  hecho, y es exactamente el defecto: si nadie puede quebrar, el dinero no
  significa nada.
- **Cambiar el club de golpe** (refundaciones, cambios de nombre, fusiones).
  Queda fuera a propósito: una institución no se reinventa en una temporada, y
  las fusiones necesitan un modelo de negociación que todavía no existe.

## Consecuencias

- La deuda de un club ya **cambia** al cruzar una frontera de temporada. La
  prueba de movilidad que comprobaba «la deuda es idéntica» se actualizó para
  comprobar lo que de verdad importa: que la deuda del club es la que dejó su
  cierre de temporada, no otra, y que moverse de categoría no la borra.
- Un universo de larga duración pierde clubes. Es intencionado y observable: la
  desaparición es una noticia con su causa y su cifra.
- Las tasas de cobro son **heurísticas declaradas** en `COLLECTION_RATES`, no
  datos observados. Lo garantizado es la asimetría entre previsión y cobro, no
  el decimal.
- Sigue sin existir mercado de fichajes, derechos de televisión ni traspasos,
  así que la escala profesional queda por debajo de la realidad. Está anotado en
  el plan y en `/acerca`.
