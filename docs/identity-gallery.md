# Identidades procedurales: revisión y extensión

La galería vive en **/identidades**. Calcula 100 instituciones ficticias con
contextos de distintos países, tipos de organización, fechas y valores. Sus
nombres pasan por el mismo generador y registro de similitud que los clubes;
sus logos pasan por el mismo constructor de identidad. No hay una lista de
100 nombres o imágenes finales.

Desde `naming/4.1.0`, la sede no es obligatoria en el nombre ni recibe una
bonificación de naturalidad. La intención territorial se sortea una vez por
club: 12% en competiciones municipales y 28% en otros ámbitos. Son preferencias,
no cuotas: la disponibilidad y la similitud pueden requerir otra candidata.
Las formas locales conservan el concepto y su idioma; un prefijo como «Club»
o «Deportivo» no basta para distinguir dos nombres iguales. La sede sigue
guardada en el club. Los nombres institucionales documentados y los clubes
ya persistidos no se renombran.

`identity/6.3.0` amplía el repertorio a 22 símbolos paramétricos. Añade aves,
toros, puentes, espigas, pinos, cactus, lunas, constelaciones, engranes y yunques.
Cuando el concepto no nombra un objeto concreto, se elige una metáfora de su
familia semántica; la pelota ya no ocupa el 40% de esas elecciones. Soles y
montañas tienen menos peso como metáforas, sin sustituirlos si el nombre los
menciona literalmente. Las composiciones heráldicas incluyen campos
cuartelados y tres figuras además de cabecera, cinta y ramas ornamentales.
Las pruebas de la colección comprueban diversidad de símbolos, no solo hashes
distintos. Los árboles guardados conservan sus diseños anteriores.

Se reutilizan el campo JSON de marca de los clubes en PostgreSQL, las semillas
derivadas del simulador, el contrato LogoSpec, el árbol de composición, la
rotulación vectorial y el renderizador SVG del backend. Se conserva Python como
único motor gráfico del dominio para evitar divergencias con la simulación.
TypeScript y SvelteKit implementan la exploración y exportación.

## Flujo

1. La identidad verbal evalúa gramáticas y conceptos según idioma e institución.
   Hay construcciones territoriales, institucionales y simbólicas, derivaciones
   morfológicas españolas y calificadores con concordancia. El repertorio es
   curado y limitado: no es un modelo lingüístico universal. Un idioma sin
   gramática mantiene el topónimo.
2. El perfil fija el nombre seleccionado, referencias, valores y dirección
   visual antes de componer candidatos. Las referencias culturales ausentes
   se declaran ausentes; las decisiones ficticias no se presentan como hechos
   históricos del territorio.
3. Las producciones tipográficas y gráficas combinan soportes opcionales,
   particiones, contornos, símbolos, repeticiones, leyendas y ornamentos.
   Las curvas de cada símbolo nuevo se calculan y quedan congeladas en el árbol.
4. La evaluación toma en cuenta matrices de los antecesores, repeticiones,
   recorte, grosor, masa visual, jerarquía, tamaños y posibles invasiones del
   texto sobre los símbolos. Son heurísticas de cajas y masas, no una garantía
   estética ni una prueba de colisiones exactas entre curvas.
5. El sistema guarda las siete variantes, la semilla, versión y perfil.
   Un cambio de algoritmo no regenera los clubes guardados. El procedimiento
   de rediseño conserva revisiones anteriores y requiere un motivo.

## Ejemplos de capacidad

La misma galería muestra CJ sobre un círculo, un elefante frontal ante un
escudo dividido y tres rosas en triángulo. Se sintetizan mediante curvas,
parámetros anatómicos, máscaras, transformaciones y repetición. No son archivos
de imágenes seleccionados por el generador. Se pueden abrir como SVG.

Los generadores extensibles están en simulation/identity/symbols.py.
Para añadir uno, registrar una función que reciba el RNG y devuelva un árbol
con contornos y cajas geométricas conservadoras. Un nombre sin generador
produce un error; nunca se sustituye silenciosamente por otro animal.
Una marca abstracta se declara abstracta en el perfil.

## Caché, exportación y compatibilidad

La galería conserva como máximo dos colecciones en una caché de proceso.
Cambiar de semilla recalcula la colección; abrir una ficha no genera un logo
nuevo. Las imágenes se cargan bajo demanda, con ETag y caché HTTP también a
través del proxy SvelteKit. Las tarjetas se muestran por grupos de 24.
Las variantes reducidas se utilizan automáticamente por debajo de 64 píxeles.

Los perfiles de clubes siguen persistiendo en PostgreSQL. La galería es una
demostración independiente y no inserta clubes en los universos. Permite
descargar SVG y la representación estructurada de cada identidad.

Para obtener artefactos offline:

```sh
.venv/bin/python scripts/identity_gallery.py --seed 20261030
.venv/bin/python scripts/identity_gallery.py --json /tmp/baseball-identities.json
```

Los árboles antiguos conservan su semántica de transformación (versión 1).
Los nuevos contenedores usan transform_version=2, que aplica traslación,
rotación y escala respecto al centro del lienzo. Las máscaras nuevas pueden
recortar por intersección o abrir espacios negativos. Estos campos tienen
valores por defecto compatibles con las marcas persistidas.

Las fuentes latinas incluyen licencia OFL y avisos en
simulation/identity/assets. Los alfabetos no cubiertos por esos contornos usan
texto Unicode y necesitan una fuente compatible en el visor.

## Comprobación

La versión 6.1 prioriza escudos sobre monogramas: campos partidos, cintas,
cabeceras, ribetes y ramas ornamentales se combinan con el símbolo del club.
Robles, torres y pelotas amplían el repertorio figurativo; la pelota representa
el deporte, no una tradición territorial supuesta. La selección y la geometría
siguen siendo reproducibles por semilla. No se regeneran clubes persistidos.

La galería muestra marcas a 256 px y abre el detalle a 384 px; en móvil usa
una columna para mantenerlas grandes. Las tarjetas de equipos muestran el
escudo completo a 160 px, la cabecera del club a 144 px y sus variantes a
224 px. Las miniaturas menores de 64 px siguen usando la versión reducida.

```sh
.venv/bin/python -m pytest simulation/tests/test_identity_gallery.py backend/tests/test_identity_gallery.py
docker compose exec -T frontend npm run check
```

Las pruebas validan la colección real, regeneración sin caché, exportación y
carga, firmas visuales distintas, semántica de los símbolos, límites, SVG,
parámetros geométricos, máscaras/repeticiones y compatibilidad de árboles.
