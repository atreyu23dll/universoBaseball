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

Dos semillas, 720 partidos cada una. **Todas las métricas dentro de la banda de
referencia.**

| Métrica | Medido | Referencia pro |
|---|---|---|
| Carreras por partido | 8.45 | 8.0 – 10.0 |
| AVG de liga | .247 | .240 – .270 |
| OBP de liga | .312 | .305 – .335 |
| SLG de liga | .416 | .390 – .440 |
| Ponches por turno | 20.0 % | 18 – 24 % |
| Boletos por turno | 8.1 % | 7 – 10 % |
| Jonrones por turno | 3.31 % | 2.5 – 3.5 % |
| Errores por partido | 0.78 | 0.50 – 0.90 |
| ERA de liga | 4.01 | 3.80 – 4.80 |
| Partidos a entradas extra | 10.1 % | 6 – 12 % |
| Carreras sucias | 5.6 % | 5 – 11 % |
| AVG del campeón de bateo | .355 | .330 – .380 |
| Porcentaje del campeón de liga | .661 | .580 – .700 |
| Desviación de victorias entre clubes | .084 | ≈ .070 |

Fuera de las bandas automáticas, medido aparte en el mismo escenario:
**4.71 entradas por apertura** con **83.5 lanzamientos** de media, y **5.4
relevistas por partido**.

## 4. Resultados — escenario municipal

El escenario modesto **debe** desviarse, y lo hace en la dirección correcta:

| Métrica | Municipal | Profesional | Dirección esperada |
|---|---|---|---|
| Errores por partido | 1.22 | 0.78 | ✔ más, defensa peor |
| Boletos por turno | 9.1 % | 7.9 % | ✔ más, menos control |
| Jonrones por turno | 2.98 % | 3.32 % | ✔ menos, menos potencia |
| ERA de liga | 4.32 | 3.96 | ✔ más alta |
| Carreras por partido | 9.34 | 8.38 | ✔ más ofensiva |
| AVG del campeón de bateo | .390 | .353 | ✔ más extremo, liga más heterogénea |

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

## 6. Rendimiento medido

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

## 7. Cómo repetir la medición

```bash
make calibrate                      # los dos escenarios, 2 semillas
python scripts/calibrate.py --scenario pro --seasons 5
```

El script sale con código 1 si el escenario **profesional** se sale de alguna
banda; las desviaciones del municipal son esperadas y no fallan.
