# Calibración de la simulación

> Medido el **20 de octubre de 2026** con `simulation` 0.1.0, motor
> `fast_pa_engine/1.0.0`, en un Linux x86-64 con Python 3.14.
> Reproducible con `python scripts/calibrate.py --seasons 2`.

## 1. Qué significa «calibrado» aquí

Nada de esto es una predicción. El motor es **plausible**, no científico: las
tasas base se eligieron para que un entorno profesional caiga dentro de los
rangos del béisbol profesional moderno, y las sensibilidades se ajustaron para
que la dispersión entre jugadores se parezca a la real. Los coeficientes
económicos y los índices de mercado **no** están calibrados contra ningún dato
económico: son heurísticas declaradas.

Tres categorías, que el código distingue con `Confidence`:

| Categoría | Qué es | Dónde |
|---|---|---|
| Calibrado empíricamente | ajustado hasta reproducir distribuciones conocidas | tasas base y sensibilidades de `simulation/baseball/rates.py` |
| Heurística declarada | fórmula nuestra, razonada pero sin validar | presupuesto, aforo, afición, profesionalización |
| Ficción | inventado para que el mundo exista | nombres, escudos, subzonas, estadios |

## 2. Metodología

`scripts/calibrate.py` genera un mundo con semilla fija, juega la temporada
regular completa turno a turno y agrega todo lo que el motor produjo. No hay
muestreo ni atajo: los números salen de los mismos box scores que la interfaz
muestra. Se comparan con bandas de referencia del béisbol profesional moderno
declaradas en `REFERENCE`, dentro del propio script.

Dos escenarios, elegidos porque deben diferir:

- **Municipal** — Liga Municipal de Ciudad Juárez, 12 clubes, 44 partidos,
  nivel resuelto por contexto (`semi_professional`, índice 0.492).
- **Profesional** — Liga Nacional de México, 16 clubes, 90 partidos, nivel
  fijado por el usuario (`professional`, índice 0.680).

## 3. Resultados — escenario profesional

Cuatro semillas, 720 partidos cada una, medido el 24 de octubre de 2026 tras la
recalibración económica de §7 bis. **Todas las métricas dentro de la banda de
referencia.** Nivel emergente del escenario: 0.667 (`established`).

| Métrica | Medido | Referencia pro |
|---|---|---|
| Carreras por partido | 8.73 | 8.0 – 10.0 |
| AVG de liga | .250 | .240 – .270 |
| OBP de liga | .317 | .305 – .335 |
| SLG de liga | .419 | .390 – .440 |
| Ponches por turno | 19.4 % | 18 – 24 % |
| Boletos por turno | 8.4 % | 7 – 10 % |
| Jonrones por turno | 3.31 % | 2.5 – 3.5 % |
| Errores por partido | 0.85 | 0.50 – 0.90 |
| ERA de liga | 4.10 | 3.80 – 4.80 |
| Partidos a entradas extra | 11.0 % | 6 – 12 % |
| Carreras sucias | 6.2 % | 5 – 11 % |
| AVG del campeón de bateo | .355 | .330 – .380 |
| Porcentaje del campeón de liga | .647 | .580 – .700 |
| Desviación de victorias entre clubes | .081 | ≈ .070 |

Fuera de las bandas automáticas, medido aparte en el mismo escenario:
**4.71 entradas por apertura** con **83.5 lanzamientos** de media, y **5.4
relevistas por partido**.

## 4. Resultados — escenario municipal

El escenario modesto **debe** desviarse, y lo hace en la dirección correcta. Su
nivel emergente bajó de 0.369 (`modest`) a **0.275 (`subsistence`)** con la
recalibración de §7 bis —un club de barrio con 50 000 pesos de presupuesto es
un club de subsistencia, que es lo que es— y las desviaciones se ensancharon en
consecuencia:

| Métrica | Municipal | Profesional | Dirección esperada |
|---|---|---|---|
| Errores por partido | 1.57 | 0.85 | ✔ más, defensa peor |
| Boletos por turno | 9.8 % | 8.4 % | ✔ más, menos control |
| Jonrones por turno | 2.14 % | 3.31 % | ✔ menos, menos potencia |
| SLG de liga | .386 | .419 | ✔ menos, menos potencia |
| OBP de liga | .335 | .317 | ✔ más, muchos boletos |
| ERA de liga | 4.15 | 4.10 | ≈ igual: más carreras pero también más sucias |
| Carreras por partido | 9.17 | 8.73 | ✔ más ofensiva |
| AVG del campeón de bateo | .374 | .355 | ✔ más extremo, liga más heterogénea |

Las diferencias **no** salen de una tabla por etiqueta: salen de
`LeagueRates.for_level()` aplicado al índice de profesionalización que el
contexto geográfico produjo, y de un pool de talento con media más baja y
dispersión mayor.

## 5. Desviaciones conocidas que no se han corregido

Dicho claro, porque la alternativa sería fingir que no existen:

1. **Dispersión de promedios individuales demasiado ancha.** Medida: sd .0382
   entre bateadores clasificados; en el béisbol profesional ronda .028. Hay más
   bateadores de .300 y de .200 de los que debería. Corregirlo exige revisar la
   generación de atributos, no solo las sensibilidades.
2. **Los abridores duran poco y el bullpen trabaja de más.** 4.71 entradas por
   apertura frente a ~5.2 del béisbol profesional actual, y 5.4 relevistas por
   partido frente a ~3.3. Los lanzamientos por apertura (83.5) sí son
   realistas: el problema es que cada entrada consume más bateadores de los que
   debería. Sin conteo real de bolas y strikes (Etapa 5) el margen de ajuste es
   limitado, y preferimos dejarlo medido antes que forzar el número con una
   regla artificial del manager.
3. **Las carreras sucias se aproximan.** El reglamento manda reconstruir la
   entrada «como habría ido sin el error». El motor usa una regla más simple:
   el corredor que llega por error, y los que lleguen después en esa entrada,
   cuentan como sucios. Da 5.9 % frente al 7-8 % habitual, y puede equivocarse
   en entradas con dos outs.
4. **Los lanzamientos por turno son una estimación**, no un conteo: no hay
   bolas ni strikes. El total por partido queda plausible, pero no es una
   medición.
5. **Nada de la economía está calibrado.** Los presupuestos generados son del
   orden de magnitud que parece razonable para el mercado, y no hay ninguna
   comprobación de que lo sean.
6. **La escala profesional está por debajo de la realidad.** Un club de la Liga
   Mexicana de Béisbol maneja bastante más que el 0,9–3,4 M MXN que sale del
   modelo bottom-up, porque faltan las fuentes que dominan ese nivel: derechos
   de televisión nacionales, traspasos y explotación comercial seria. No se
   finge ninguna de ellas —no hay partida que las represente— y entran en la
   Etapa 4. El modelo captura bien la escala de base y razonablemente la
   semiprofesional; la profesional la subestima, y se sabe.
7. **Los coeficientes económicos son heurísticas sin calibrar.** Las cuotas, el
   gasto publicitario por habitante, la tasa de afiliación, el precio de la
   entrada y los costes por partida están en
   `simulation/economy/club_finances.py` y `simulation/economy/market.py`,
   todos expresados en múltiplos del coste mensual de referencia del territorio
   y todos elegidos por plausibilidad, no medidos. Lo que está garantizado es la
   **trazabilidad** de cada importe —cada partida dice su causa y su base—, no
   su exactitud.
8. **El reescalado por ascenso y descenso es una heurística sin referencia.**
   Al cambiar de categoría, el presupuesto del club se mueve hacia el factor de
   liga de su nueva competición —la misma función que usa la generación,
   `context.league_budget_factor`— una fracción `budget_adaptation` (por
   omisión 0.5), con un tope de ×2 o ÷2 por temporada. Los dos números están
   elegidos para que no haya saltos absurdos, no medidos contra nada: no
   conocemos datos públicos del efecto económico de un ascenso en una liga de
   béisbol comparable. La reputación se mueve 0.04 por temporada en el ámbito
   nacional, con el mismo criterio. Ambos quedan como parámetros a calibrar en
   la Etapa 4, cuando exista libro mayor y se pueda medir si un club recién
   ascendido sobrevive.

9. **La base social usa la tasa de afiliación como base de los seguidores.**
   `AFFILIATION_RATE` (0.0004: cuatro personas de cada diez mil) mide a quien
   **paga cuota** en un club de la zona, y `generate_clubs` la usa como base de
   la afición multiplicándola por `3 + 12 × cultura`. Son dos poblaciones
   distintas: un club profesional tiene espectadores que no son socios. Con
   mercados de estado el resultado cae en rango plausible —un club de la liga
   nacional sale con 3 000 a 44 000 seguidores y 700 a 9 700 espectadores por
   partido—, pero con mercados de ciudad repartidos entre varios clubes se queda
   corto: en el fixture curado, un club «profesional» de Ciudad de México sale
   con unos 4 000 seguidores y ~900 espectadores. Queda medido y sin corregir:
   tocar esa cadena mueve cuotas, patrocinio y taquilla a la vez, y la
   corrección honesta es separar socios de seguidores, no retocar el
   multiplicador.

## 6. Reajustes de calibración registrados

| Fecha | Parámetro | Antes | Después | Por qué |
|---|---|---|---|---|
| 22/10/2026 | `BASE_HOMERUN` | 0.0275 | 0.0245 | Al corregir la edad al corte del reglamento, la población envejeció medio año de media —antes un jugador «de 25» tenía 24,5 porque la fecha de nacimiento se sorteaba sin mirar el corte— y el escenario profesional se fue a 0.0371 jonrones por turno frente a la banda [0.025, 0.035]. Con 0.0245 queda en 0.0319. |
| 22/10/2026 | `LEVEL_SCALE` | — (nuevo) | 2.96 | Función de transferencia de recursos a nivel de juego. Se ancla pidiendo que una liga nacional profesional, cuyos clubes reúnen del orden de 100 meses de gasto doméstico, caiga en 0.68, que es el nivel al que el motor reproduce béisbol profesional: `log10(103)/0.68 ≈ 2.96`. |

| 24/10/2026 | Coeficientes económicos y orden del cálculo | ver §7 bis | ver §7 bis | Una liga llanera municipal daba presupuestos de 11 a 51 meses de gasto doméstico. Cinco causas de modelo —aforo desde el tamaño de la ciudad, precio de entrada único, bolsa publicitaria repartida entera, respaldo privado por etiqueta de gobierno, costes de club con empleados— y una sexta al corregirlas: la liga nacía quebrada porque los ingresos se calculaban antes de saber lo que cuesta la temporada. |

| 25/10/2026 | Topes de aforo, resolución de mercados y divisor de meses de caja | ver abajo | ver abajo | Un universo real tenía **todos** los aforos clavados en el tope de su acuerdo de sede (2 500 un campo público, 18 000 uno alquilado), porque la demanda calculada los superaba por diez o veinte veces. Tres causas encadenadas: una región importada de GeoNames entraba sin población y heredaba la del país —cada estado mexicano simulado con 131,9 millones de habitantes—, el país se usaba como un único mercado, y los topes eran fijos y pequeños. Con ellas, la afición de un club salía en cientos de miles y el tope era la única causa del aforo. Además, la caja del club se medía contra el gasto mensual de **un hogar**, así que el umbral para invertir en la sede estaba siempre abierto. |

Detalle del cuarto: los topes pasan a escalar con la infraestructura del mercado
(campo público 2 000 + 8 000 × infra; alquilado 12 000 + 38 000 × infra; propio
18 000 + 44 000 × infra), la población de una división administrativa se agrega
de sus localidades sin contar dos veces una ciudad y sus secciones, el país deja
de ser mercado si tiene algo utilizable debajo, y el divisor de meses de caja es
el gasto mensual del propio club con umbral de 12 meses. Medido sobre la
geografía real del usuario: una liga nacional profesional de cinco clubes pasa de
cuatro clubes en una plaza llamada «Mexico» con aforos 2 500/18 000/18 000/18 000
a cinco clubes en cinco estados distintos con aforos de 1 750 a 16 700, ninguno
en su tope.

Los reajustes son consecuencia de corregir el modelo, no de perseguir un
número: el primero reequilibra una tasa después de arreglar un error de edades,
el segundo fija la escala de una función que antes no existía porque el nivel se
elegía a mano en un formulario, y el tercero sustituye coeficientes que no
miraban la causa que tenían al lado.

**Efecto del tercero sobre el motor de partidos**, comprobado con `make
calibrate` el mismo día: el escenario profesional **no se mueve de banda** en
ninguna métrica. El municipal baja de nivel `modest` a `subsistence`, que es lo
que corresponde a un club de 50 000 pesos de presupuesto, y sus desviaciones se
ensanchan en la dirección esperada (§4). No hizo falta retocar ninguna tasa del
juego: bajar los presupuestos de una liga de barrio hace que juegue peor, y eso
es el comportamiento correcto, no un efecto secundario que haya que compensar.

## 7. Resultados del modelo económico bottom-up

Medido con el fixture mexicano, 12 clubes, 44 partidos por club, el 24 de
octubre de 2026, **después** de la recalibración de §7 bis:

| Escenario | Mediana | Rango | Mediana en MXN |
|---|---|---|---|
| Municipal · llanera | 6,2 meses | 3,7 – 11,7 | 73 969 |
| Municipal · escolar-formativa | 6,2 meses | 3,7 – 9,4 | 73 969 |
| Municipal · amateur organizada | 5,8 meses | 3,8 – 8,1 | 69 683 |
| Municipal · semiprofesional | 5,1 meses | 4,7 – 15,2 | 61 417 |
| Municipal · profesional | 7,4 meses | 5,0 – 21,3 | 89 079 |
| Nacional · amateur organizada | 47,8 meses | 45,4 – 74,7 | 573 395 |
| Nacional · semiprofesional | 42,4 meses | 40,0 – 95,1 | 509 030 |
| Nacional · profesional | 44,5 meses | 44,4 – 57,3 | 534 047 |

La columna que importa es la primera: **la modalidad no mueve la mediana**
(profesional entre llanera = 1,19×, y la prueba `test_d02` falla por encima de
2×). Lo que la mueve es el territorio: pasar de municipal a nacional multiplica
por siete, y eso sale de los mercados, de la audiencia y de los viajes.

## 7 bis. Recalibración del 24 de octubre de 2026

El usuario observó una liga llanera municipal con mediana de **136 427 MXN** y
un club en **614 398**: 11 y 51 meses de gasto de un hogar para equipos sin
propietario. Al desglosarlo aparecieron cinco defectos, todos de causa y no de
escala:

| Defecto | Qué hacía | Corrección |
|---|---|---|
| **Aforo desde el tamaño de la ciudad** | Un club con 1 000 seguidores recibía un recinto para 15 000 porque Juárez es grande; la taquilla se calculaba sobre ese público imaginario | Las gradas se dimensionan para **el público del club** (base social × la parte que acude × holgura), con el acuerdo de sede como tope |
| **Precio de entrada único** | 48 MXN por entrar a un campo de barrio, lo mismo que a un estadio | El precio sale del recinto: de 10 MXN de cooperación en un campo sin accesos a 60 en uno de 12 000 de aforo |
| **La bolsa publicitaria se repartía entera** | Los clubes de una competición se repartían toda la publicidad deportiva de su zona, dieran la audiencia que dieran: 194 746 MXN de patrocinio para un club con 973 seguidores | Dos topes y manda el menor: la bolsa finita de la zona (ADR 0005) **y** lo que un anunciante paga por seguidor |
| **Respaldo privado por forma de gobierno** | Un rango fijo por etiqueta de gobierno: 2–14 meses para `business_backed`, fuera un club de barrio o uno nacional | El mismo rango escalado por la audiencia del club: quien respalda pone en proporción a lo que el club mueve |
| **Costes de club formal para un club autogestionado** | 2 400 MXN por jugador en material y uniformes, 960 por partido de permiso de campo itinerante, 540 de arbitraje | Coeficientes a la baja y, donde el reglamento no admite pagar al jugador, la mitad del equipo personal la pone él: ahí el jugador no es un empleado |

Y un sexto que solo se vio al bajar los costes: **la liga nacía quebrada**, con
6 ó 7 de 12 clubes incapaces de cubrir sus obligaciones el primer año. Dos
causas encadenadas:

1. El club cobraba cuota a 2, 7 u 8 personas teniendo 26 inscritos, porque la
   base de socios salía solo de la población captable de la zona. En una
   competición sin salarios los que pagan la cuota son **los propios
   jugadores**, así que la base no puede ser menor que la plantilla.
2. **El orden del cálculo estaba invertido.** Se estimaban los ingresos y
   después se miraba si cubrían los gastos. Un club de barrio funciona al
   contrario: primero sabe lo que cuesta la temporada —árbitros, campo, viajes,
   inscripción— y después reparte entre los que juegan. Ahora los gastos
   obligatorios se calculan primero y **la cooperación se ajusta a ellos**, con
   un tope de 0,06 del coste mensual (unos 720 MXN al mes por jugador) porque
   por encima de eso la gente deja de apuntarse.

Con las dos correcciones, las cuotas de una llanera quedan en 0,022–0,027 del
coste mensual (265–325 MXN por jugador y mes, que es la cooperación real) y el
déficit baja a 0 ó 1 club de cada ocho. El que queda en rojo es **el que tocó el
tope de la cuota**: necesitaría más de 720 MXN mensuales por jugador para
sostener su sede alquilada. Ese déficit ya no es un artefacto del modelo, es un
club que no se sostiene, y es lo que el cierre de temporada de P5 debe liquidar.

Resultado para el caso observado, mismo territorio y mismas reglas:

| | Antes | Después |
|---|---|---|
| Mediana | 136 427 MXN (11,4 meses) | 73 969 MXN (6,2 meses) |
| Club mayor | 614 398 MXN (51,2 meses) | 140 000 MXN (11,7 meses) |
| Aforos | 850 – 15 150 | 120 – 850 |
| Clubes sin cubrir obligaciones | 6–7 de 12 | 1–2 de 12 |

Ninguna de las correcciones mira la modalidad: todas pasan por una causa
—público, recinto, audiencia, quién es empleado y quién no— que ya existía en el
modelo y no se estaba usando. Los guardarraíles `test_d03` y `test_d03b` fijan
la banda y vigilan que no se vuelva ni a inflar ni a quebrar.

Lo que **sigue sin resolverse** y se sabe: la base social de un club nacional
profesional sale del orden de 10 000 seguidores, cuando un club de la Liga
Mexicana tiene cientos de miles. De ahí vienen a la vez el aforo modesto de esos
clubes (2 500–3 800) y su presupuesto corto. Es el mismo hueco que ya estaba
anotado —sin derechos de televisión ni traspasos— visto desde el otro lado.

Lo que esta tabla demuestra y lo que no:

- **Sí demuestra** que la diferencia entre una liga de barrio y una nacional sale
  del tamaño de los mercados, de la audiencia y de los viajes, no de una
  etiqueta: la misma modalidad en el mismo territorio no mueve los importes
  (`test_d02_la_modalidad_no_decide_el_patrimonio`), y la desigualdad dentro de
  una misma competición llega a 3,7× entre el club más modesto y el mayor.
- **No demuestra** que los importes sean correctos. Son estimaciones con fuente
  y confianza declaradas, sin ninguna comprobación contra contabilidad real de
  clubes de béisbol.

## 8. Rendimiento medido

| Escenario | Partidos | Partidos/s | Proyección |
|---|---|---|---|
| Municipal, 12 clubes | 264 | ≈ 520 | temporada en 0.5 s |
| Profesional, 16 clubes | 720 | ≈ 520 | temporada en 1.4 s |

Un hilo, sin optimizar. A ese ritmo, el escenario de estrés de la
especificación —50.000 partidos— tarda del orden de **100 segundos** de CPU de
simulación pura, sin contar la persistencia, que en el avance real domina el
coste. Esto es una medición en esta máquina, **no** un SLA: la cifra a vigilar
está en `simulation/tests/test_performance.py`, que falla si el motor se
degrada por debajo de 150 partidos/s.

## 9. Cómo repetir la medición

```bash
make calibrate                      # los dos escenarios, 4 semillas
python scripts/calibrate.py --scenario pro --seasons 6
```

**Cuántas semillas hacen falta.** `make calibrate` usa cuatro y no dos a
propósito. Con dos semillas, las métricas que son proporciones de partidos
—`extra_inning_share` ronda 0.12 con una banda de ancho 0.06— tienen un error de
muestreo comparable al ancho de su propia banda, y la comprobación pasa o falla
por un partido de diferencia. Una medición que depende de eso no mide nada. Las
métricas por turno al bate (AVG, OBP, jonrones) son mucho más estables porque
cada temporada aporta decenas de miles de turnos.

El script sale con código 1 si el escenario **profesional** se sale de alguna
banda; las desviaciones del municipal son esperadas y no fallan.
