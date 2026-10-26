# ADR 0013 — Retirada de la generación de plantillas

- **Fecha:** 25 de octubre de 2026
- **Estado:** aceptado e implementado
- **Contexto:** decisión del usuario sobre el anexo de personas; sustituye en la
  práctica a la parte de población deportiva del FIX V2 de Fase 1
- **Se apoya en:** ADR 0012 (motor universal de personas) y la auditoría
  [H0](../personas-h0-auditoria.md)

## Problema

El repositorio tenía dos maneras de crear gente que no se parecían en nada.

La que acababa de nacer —`simulation.persons` y `person_service`— crea
**personas del universo**: alguien que vive en un territorio, con sus 52
atributos, sin oficio ni club, y cuya identidad no depende de ninguna
competición.

La que venía de antes creaba **jugadores**: al generar una liga se inventaba una
población deportiva por mercado, se repartía entre los clubes con un draft de
información imperfecta y quedaban agentes libres. Esa gente nacía con posición
de juego, valoración global y seis números de cognición, dentro del acto de
abrir una competición.

Mantener las dos obligaba a decidir, en cada paso siguiente —organigramas,
cargos, relaciones, decisiones—, con cuál de los dos conceptos de persona se
trabajaba. Y la segunda, además, prejuzga lo que todavía no está decidido: cómo
una persona pasa a jugar en un club. Eso es una **mecánica de selección** que no
está definida, y el draft existente era una respuesta a una pregunta que no se
había hecho.

## Decisión

Se retira por completo la generación de plantillas. Queda una sola puerta por la
que entra gente al universo: `person_service.materialize_person`.

### Lo que se fue

| Pieza | Qué hacía |
|---|---|
| `generate_talent_pool` | Inventaba la población deportiva de cada competición |
| `_make_person` | Creaba un jugador con sus atributos de béisbol |
| `roster_plan`, `_POSITION_PLAN` | Repartía una plantilla entre posiciones |
| `assign_rosters`, `_pick_order` | El draft con información imperfecta |
| `PoolMember`, `pool_member_for` | El candidato del pool y lo que los clubes veían de él |
| `available_pool`, `next_serials` | Ofrecer al motor la gente disponible del territorio |
| `store_generated_profile` | Perfil universal de un jugador recién generado |
| `_dominant_country` | País dominante de un territorio, solo para nombrar jugadores |

`GeneratedWorld` conserva `people` y `free_agents`, **siempre vacíos**: los
consume la API y volverán a llenarse el día en que haya mecánica de selección.

### Lo que se queda, y por qué

- **La elegibilidad por edad** (`cutoff_date_for`, `age_range`, `is_eligible`).
  No es una forma de crear gente: es una regla del reglamento —con corte al
  inicio de temporada, quien cumple años en octubre juega toda la temporada en
  la categoría que tenía en marzo— y la mecánica nueva la necesitará igual. Hoy
  no tiene consumidor y se dice en su módulo.
- **`roster_size` en las cuentas del club.** Un club presupuesta equipar y
  sostener a N personas aunque todavía no tenga ninguna. Era una causa legítima
  de sus gastos antes y lo sigue siendo.
- **El motor de partidos, entero.** No se toca una línea: sabe jugar, y lo que
  le falta es a quién. Sus pruebas construyen sus propias alineaciones en
  `simulation/tests/factories.py`, que es laboratorio y no generación: no hay
  mercados, ni territorio, ni identidad persistente, ni nada que entre en un
  universo.

### Los partidos se desactivan diciéndolo

Un club nace sin jugadores, así que no hay partido que simular.
`sim_service` lo comprueba antes de jugar y falla con un error tipado,
`ROSTERS_MISSING`, que nombra a los clubes sin plantilla y explica la causa. No
se simula un encuentro entre dos conjuntos vacíos ni se inventa un resultado.

Un universo sigue pudiendo crearse, elegir territorio, generar clubes con su
gobierno, su sede y sus cuentas, inscribirlos y publicar su calendario. Lo que
no puede es jugar.

### Las pruebas lo dicen en voz alta

Las **36 pruebas** que necesitaban jugadores quedan marcadas
`xfail(strict=True)` con su causa escrita. `strict` importa: el día en que
exista la mecánica de selección esas pruebas pasarán, y una `xfail` estricta que
pasa **falla la batería**. Así nadie se olvida de reactivarlas, que es
exactamente lo que el anexo §18 pide: no ocultar defectos ni poner nada en verde
simplificando lo que comprueba.

Tres pruebas no se marcaron, se **reescribieron en positivo**, porque lo que
comprobaban sigue siendo comprobable al revés: generar una competición no crea
personas, abrir dos ligas no crea ninguna, y el club nace con sede y cuentas y
con la plantilla vacía. Si algún día vuelven a crearse jugadores por ahí, esas
tres fallarán.

## Alternativas descartadas

- **Dejar las plantillas hasta tener la mecánica nueva.** Habría obligado a
  mantener dos conceptos de persona en paralelo y a decidir con cuál trabajaba
  cada hito siguiente. El usuario lo descartó explícitamente.
- **Conservar el draft como «mecánica provisional».** Lo provisional que
  funciona se queda, y este draft prejuzga el diseño de lo que viene.
- **Rellenar plantillas con un comando aparte** para que el universo siguiera
  jugando. Se valoró y se descartó: sería la misma generación con otro nombre.
- **Marcar también las pruebas del motor de partidos.** Habría dejado el motor
  sin red de seguridad por una causa que no es suya: no sabe de dónde sale su
  gente. Construyen sus alineaciones y siguen corriendo.

## Consecuencias

- **El universo no puede avanzar el reloj.** Es el precio aceptado, y está
  dicho en un error tipado en vez de en un fallo oscuro.
- **36 pruebas en `xfail(strict=True)`**: ocho de vida institucional, doce de
  movilidad entre competiciones, seis de divisiones, cuatro de la vertical
  completa, cuatro de generación y dos más. Son la lista de lo que la mecánica
  de selección tendrá que devolver a la vida.
- **La batería pasó de 4 min 25 s a 36 s.** No es una mejora: es la medida de
  cuánto del proyecto dependía de generar y simular jugadores.
- **La liquidación de temporada, los ascensos y las divisiones siguen
  implementados y sin tocar.** No se han borrado: están esperando que haya
  partidos que las alimenten.
- Lo siguiente es lo que el usuario pidió a cambio: que al crear un club nazcan
  sus **propietarios o responsables** como personas reales del universo, según
  la plantilla de organigrama que defina. Mientras no esté, un club es una
  institución sin una sola persona dentro.
