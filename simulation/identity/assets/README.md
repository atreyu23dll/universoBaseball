# Contornos tipográficos

`brand-type-v1.json` contiene un subconjunto latino de glifos Noto convertido
a coordenadas relativas a la altura de mayúsculas. No contiene logos.
El generador calcula las composiciones y persiste sus curvas en cada identidad.
La distribución derivada se denomina **Brand Type v1**; véanse OFL.txt y
FONT-NOTICES.txt para licencia y atribuciones.

Para recompilar, instalar fonttools en un entorno de desarrollo y ejecutar:

```sh
python scripts/build_brand_type.py --fonts /ruta/a/fuentes/noto
```

La ejecución de la aplicación no necesita fonttools ni fuentes instaladas.
Alfabetos fuera del subconjunto conservan texto Unicode con fuentes del visor.

La dirección identity/5.0.0 genera firmas tipográficas, monogramas, sellos y
banderines. No pretende producir mascotas ilustradas realistas. Las identidades
persistidas conservan su diseño anterior: cambiar el generador no las migra.

Revisión visual reproducible:

```sh
python scripts/crest_showcase.py
```

Abre crests-review.svg para comparar fondos claros/oscuros y tamaños de
24, 40 y 56 píxeles. La ruta de escudos elige la variante reducida por debajo
de 64 píxeles para las nuevas marcas; las variantes explícitas no se sustituyen.
