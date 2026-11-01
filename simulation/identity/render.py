"""El único intérprete del logo: especificación → SVG.

Vive en Python y no en el componente del frontend, y eso es una decisión, no
una casualidad. Con el intérprete aquí:

- un logo se puede **exportar** —endpoint `.svg`, favicon, imagen para
  compartir— sin abrir un navegador;
- se puede **probar**: el SVG es texto, así que una prueba compara cadenas y
  una hoja de contactos se mira de un golpe;
- y no hay dos implementaciones que puedan separarse. Antes la semántica del
  contrato vivía en una cadena de `if/else` dentro de un `.svelte`: cualquier
  otro consumidor —un export, un correo, una miniatura— habría tenido que
  reimplementarla y habría divergido en una semana.

Todo lo que sale de aquí es SVG estático sin scripts, y el texto va escapado:
un escudo es un dato, no un documento ejecutable.
"""

from __future__ import annotations

import math
import re
from xml.sax.saxutils import escape

from simulation.identity.motifs import Primitive, primitives_for
from simulation.identity.spec import (
    CANVAS,
    CompositionNode,
    Layer,
    LogoSpec,
    MotifLayer,
    NodeKind,
    Palette,
    PathLayer,
    Shape,
    ShapeLayer,
    TextLayer,
    TextLayout,
    Typography,
)

#: Siluetas de soporte, en coordenadas del lienzo (0–100).
SHAPE_PATHS: dict[Shape, str] = {
    Shape.SHIELD: "M50 3 L95 17 V53 C95 78 73 95 50 100 C27 95 5 78 5 53 V17 Z",
    Shape.CIRCLE: "M50 4 A46 46 0 1 1 49.9 4 Z",
    Shape.DIAMOND: "M50 2 L98 50 L50 98 L2 50 Z",
    Shape.SQUARE: "M7 7 H93 V93 H7 Z",
    Shape.HEXAGON: "M50 3 L92 27 V73 L50 97 L8 73 V27 Z",
    Shape.BANNER: "M8 5 H92 V72 L50 98 L8 72 Z",
    Shape.TRIANGLE: "M50 7 L95 91 H5 Z",
    Shape.RING: "M50 6 A44 44 0 1 1 49.9 6 Z",
    Shape.ARCH: "M50 4 A46 46 0 0 1 96 50 V96 H4 V50 A46 46 0 0 1 50 4 Z",
}

#: Familias tipográficas por estilo. Se nombran varias para que el escudo se
#: parezca a sí mismo en cualquier máquina.
#: Caras con alfabetos no latinos, añadidas al final de cada pila. El motor
#: rotula con contornos propios siempre que puede, pero un nombre en japonés,
#: coreano, chino o árabe no está en esa fuente y acaba como texto del sistema:
#: sin estos nombres, el navegador elige cualquier cosa —o dibuja cuadraditos—.
#: Que el equipo tenga la fuente instalada ya no depende del motor; que se le
#: pida la correcta, sí.
_FALLBACK_NO_LATINO = (
    "'Noto Sans CJK JP','Noto Sans JP','Hiragino Sans','Yu Gothic','Meiryo',"
    "'Noto Sans CJK KR','Malgun Gothic','Apple SD Gothic Neo',"
    "'Noto Sans CJK SC','PingFang SC','Microsoft YaHei',"
    "'Noto Naskh Arabic','Geeza Pro',Tahoma"
)

FONT_STACK: dict[Typography, str] = {
    Typography.BLOCK: f"'Arial Black','Helvetica Neue',Helvetica,{_FALLBACK_NO_LATINO},sans-serif",
    Typography.SLAB: f"Rockwell,'Roboto Slab',Georgia,{_FALLBACK_NO_LATINO},serif",
    Typography.SCRIPT: f"'Brush Script MT','Segoe Script',{_FALLBACK_NO_LATINO},cursive",
    Typography.CONDENSED: (
        f"'Arial Narrow',Impact,'Haettenschweiler',{_FALLBACK_NO_LATINO},sans-serif"
    ),
    Typography.GEOMETRIC: f"Futura,'Century Gothic','Avenir Next',{_FALLBACK_NO_LATINO},sans-serif",
}


def _fmt(value: float) -> str:
    """Un número corto: el SVG de un escudo no necesita doce decimales."""
    texto = f"{value:.2f}".rstrip("0").rstrip(".")
    return texto or "0"


def _primitive_svg(
    primitive: Primitive,
    size: float,
    fill: str,
    stroke: str,
    width: float,
    palette: Palette | None = None,
) -> str:
    """Una primitiva de la caja 0–1 llevada a `size` unidades del lienzo."""
    escala = size
    trazo = f' stroke="{stroke}" stroke-width="{_fmt(width)}"' if stroke != "none" else ""
    clase = primitive["kind"]
    if clase == "path":
        assert palette is not None
        color = palette.resolve(primitive["color"])
        outline = palette.resolve(primitive["outline"])
        return (
            f'<path d="{primitive["d"]}" transform="scale({_fmt(size)})" '
            f'fill="{color}" stroke="{outline}" stroke-width="{primitive["width"]}" '
            'stroke-linecap="round" stroke-linejoin="round"/>'
        )
    if clase == "poly":
        puntos = " ".join(f"{_fmt(x * escala)},{_fmt(y * escala)}" for x, y in primitive["points"])
        return f'<polygon points="{puntos}" fill="{fill}"{trazo}/>'
    if clase == "circle":
        return (
            f'<circle cx="{_fmt(primitive["cx"] * escala)}" cy="{_fmt(primitive["cy"] * escala)}"'
            f' r="{_fmt(primitive["r"] * escala)}" fill="{fill}"{trazo}/>'
        )
    if clase == "ring":
        return (
            f'<circle cx="{_fmt(primitive["cx"] * escala)}" cy="{_fmt(primitive["cy"] * escala)}"'
            f' r="{_fmt(primitive["r"] * escala)}" fill="none" stroke="{fill}"'
            f' stroke-width="{_fmt(primitive["width"] * escala)}"/>'
        )
    if clase == "line":
        puntos = " ".join(f"{_fmt(x * escala)},{_fmt(y * escala)}" for x, y in primitive["points"])
        return (
            f'<polyline points="{puntos}" fill="none" stroke="{fill}"'
            f' stroke-width="{_fmt(primitive["width"] * escala)}"'
            ' stroke-linecap="round" stroke-linejoin="round"/>'
        )
    if clase == "crescent":
        # Una luna es un círculo al que otro le quita un bocado. Se dibuja con
        # una máscara para que funcione sobre cualquier fondo.
        cx, cy, r = primitive["cx"] * escala, primitive["cy"] * escala, primitive["r"] * escala
        bocado = primitive["bite"] * escala
        ident = f"bite{int(cx)}{int(cy)}{int(r)}"
        return (
            f'<mask id="{ident}"><circle cx="{_fmt(cx)}" cy="{_fmt(cy)}" r="{_fmt(r)}"'
            ' fill="#fff"/>'
            f'<circle cx="{_fmt(cx + bocado)}" cy="{_fmt(cy - bocado * 0.4)}" r="{_fmt(r * 0.86)}"'
            ' fill="#000"/></mask>'
            f'<circle cx="{_fmt(cx)}" cy="{_fmt(cy)}" r="{_fmt(r)}" fill="{fill}"'
            f' mask="url(#{ident})"/>'
        )
    raise ValueError(f"primitiva desconocida: {clase}")


#: Ancho medio de un glifo en mayúsculas, como fracción del cuerpo de la letra.
#: El renderizador no tiene métricas reales de fuente —ni serían las mismas en
#: cada máquina—, así que estima con esto si un nombre cabe. Vale para saber
#: cuándo hay que encoger la letra, no para componer tipografía fina.
GLYPH_WIDTH: dict[Typography, float] = {
    Typography.BLOCK: 0.66,
    Typography.SLAB: 0.62,
    Typography.SCRIPT: 0.50,
    Typography.CONDENSED: 0.46,
    Typography.GEOMETRIC: 0.60,
}

#: Lo que mide el lienzo descontando el borde: ningún texto debe pasar de aquí.
TEXT_BUDGET = 88.0

#: Mitad de la altura de una mayúscula, en múltiplos del cuerpo. Sirve para
#: centrar el texto a mano: `dominant-baseline="central"` lo calcula desde las
#: métricas de la fuente, y una tipografía de respaldo con ascendentes enormes
#: —las de tipo script lo son— empuja las letras fuera del escudo. Esto siempre
#: centra las mayúsculas, dibuje el navegador la fuente que dibuje.
CAP_CENTER = 0.35


def _arc_radius(size: float, arriba: bool) -> float:
    """Radio del semicírculo por el que corre un nombre curvado.

    Las letras crecen hacia el centro del escudo desde su línea base, así que
    un cuerpo grande sobre un arco fijo se sale del lienzo por arriba. El arco
    se cierra en su lugar: cuanto mayor la letra, menor el radio.
    """
    margen = 0.80 * size if arriba else 0.28 * size
    limite = (43.0 if arriba else 41.0) - margen
    return max(min(36.0, limite), 18.0)


def _fit(layer: TextLayer, caracteres: int, presupuesto: float) -> tuple[float, float]:
    """Cuerpo y espaciado que hacen caber `caracteres` en `presupuesto`.

    Un nombre largo con el cuerpo que pidió el compositor se sale del escudo y
    aparece recortado por el `viewBox`. Antes que recortarlo, se encoge: el
    escudo sigue diciendo su nombre entero.
    """
    unidad = layer.size * GLYPH_WIDTH[layer.typography] + layer.letter_spacing
    ancho = caracteres * unidad
    if ancho <= presupuesto or ancho <= 0:
        return layer.size, layer.letter_spacing
    factor = presupuesto / ancho
    return layer.size * factor, layer.letter_spacing * factor


def _text_svg(layer: TextLayer, palette: Palette) -> str:
    relleno = palette.resolve(layer.fill)
    borde = palette.resolve(layer.stroke)
    familia = FONT_STACK[layer.typography]

    if layer.layout in (TextLayout.ARC, TextLayout.ARC_BELOW):
        radio = _arc_radius(layer.size, layer.layout is TextLayout.ARC)
        cuerpo, espaciado = _fit(layer, len(layer.text), 3.1416 * radio * 0.94)
    elif layer.layout is TextLayout.STACKED:
        palabra_larga = max((len(p) for p in layer.text.split()), default=len(layer.text))
        cuerpo, espaciado = _fit(layer, palabra_larga, TEXT_BUDGET)
    elif layer.layout is TextLayout.VERTICAL:
        # Aquí el límite es la altura: una letra debajo de otra.
        cuerpo = min(layer.size, TEXT_BUDGET / max(len(layer.text) * 0.92, 1))
        espaciado = layer.letter_spacing
    else:
        cuerpo, espaciado = _fit(layer, len(layer.text), TEXT_BUDGET)

    comun = (
        f'font-family="{familia}" font-size="{_fmt(cuerpo)}" font-weight="900"'
        f' letter-spacing="{_fmt(espaciado)}" fill="{relleno}"'
        + (
            f' stroke="{borde}" stroke-width="{_fmt(layer.stroke_width)}" paint-order="stroke"'
            if borde != "none" and layer.stroke_width
            else ""
        )
    )
    texto = escape(layer.text)

    if layer.layout in (TextLayout.ARC, TextLayout.ARC_BELOW):
        # El nombre curvado sobre —o bajo— el escudo: la «topología especial»
        # que un `<text>` recto no puede dar. El camino va en coordenadas del
        # lienzo, así que esta capa ignora su ancla a propósito.
        arriba = layer.layout is TextLayout.ARC
        ident = f"arc{int(cuerpo * 10)}r{int(radio * 10)}{'u' if arriba else 'd'}"
        base = 46.0 if arriba else 56.0
        camino = (
            f"M{_fmt(50 - radio)} {_fmt(base)} A{_fmt(radio)} {_fmt(radio)}"
            f" 0 0 {'1' if arriba else '0'} {_fmt(50 + radio)} {_fmt(base)}"
        )
        return (
            f'<path id="{ident}" d="{camino}" fill="none"/>'
            f'<text {comun} text-anchor="middle">'
            f'<textPath href="#{ident}" startOffset="50%">{texto}</textPath></text>'
        )

    if layer.layout is TextLayout.STACKED:
        palabras = texto.split() or [texto]
        alto = cuerpo * 1.05
        inicio = -(len(palabras) - 1) * alto / 2 + CAP_CENTER * cuerpo
        lineas = "".join(
            f'<tspan x="0" dy="{_fmt(alto if indice else inicio)}">{palabra}</tspan>'
            for indice, palabra in enumerate(palabras)
        )
        return f'<text {comun} text-anchor="middle">{lineas}</text>'

    if layer.layout is TextLayout.VERTICAL:
        alto = cuerpo * 0.92
        inicio = -(len(texto) - 1) * alto / 2 + CAP_CENTER * cuerpo
        lineas = "".join(
            f'<tspan x="0" dy="{_fmt(alto if indice else inicio)}">{caracter}</tspan>'
            for indice, caracter in enumerate(texto)
        )
        return f'<text {comun} text-anchor="middle">{lineas}</text>'

    return f'<text {comun} text-anchor="middle" dy="{_fmt(CAP_CENTER * cuerpo)}">{texto}</text>'


def _layer_svg(layer: Layer, palette: Palette) -> str:
    origen_x, origen_y = layer.placement.origin()
    giro = f" rotate({_fmt(layer.placement.rotate)})" if layer.placement.rotate else ""
    opacidad = f' opacity="{_fmt(layer.opacity)}"' if layer.opacity < 1 else ""
    if isinstance(layer, PathLayer):
        transform = (
            f"translate({_fmt(origen_x)} {_fmt(origen_y)}){giro} "
            f"scale({_fmt(layer.placement.scale)}) translate(-50 -50)"
        )
        return (
            f'<g transform="{transform}"{opacidad}><path d="{layer.d}" '
            f'fill="{palette.resolve(layer.fill)}" stroke="{palette.resolve(layer.stroke)}" '
            f'stroke-width="{layer.stroke_width}" stroke-linejoin="round" '
            'stroke-linecap="round" paint-order="stroke fill"/></g>'
        )

    if isinstance(layer, ShapeLayer):
        relleno = palette.resolve(layer.fill)
        borde = palette.resolve(layer.stroke)
        trazo = (
            f' stroke="{borde}" stroke-width="{_fmt(layer.stroke_width)}"'
            if borde != "none" and layer.stroke_width
            else ""
        )
        if layer.shape is Shape.RING:
            # El anillo es la silueta de un disco: su color vive en `fill`, y el
            # trazo lo dibuja. Un marco transparente llega con fill="none" y el
            # color en `stroke`; sin este respaldo salía fill="none"
            # stroke="none" —una capa que ocupa su sitio y no se ve.
            tinta = relleno if relleno != "none" else borde
            if tinta == "none":
                return ""
            grosor = layer.stroke_width if relleno == "none" and layer.stroke_width else 7.0
            relleno = "none"
            trazo = f' stroke="{tinta}" stroke-width="{_fmt(grosor)}"'
        cuerpo = f'<path d="{SHAPE_PATHS[layer.shape]}" fill="{relleno}"{trazo}/>'
        # Las siluetas ya vienen en coordenadas del lienzo: se escalan desde el
        # centro para que un marco pueda ser más pequeño que el soporte.
        escala = layer.placement.scale
        transformacion = (
            f"translate({_fmt(origen_x)} {_fmt(origen_y)}){giro} "
            f"scale({_fmt(escala)}) translate(-50 -50)"
        )
        return f'<g transform="{transformacion}"{opacidad}>{cuerpo}</g>'

    if isinstance(layer, MotifLayer):
        tamano = CANVAS * 0.5 * layer.placement.scale
        relleno = palette.resolve(layer.fill)
        borde = palette.resolve(layer.stroke)
        piezas = primitives_for(layer.motif, layer.params)
        copias: list[str] = []
        for indice in range(layer.repeat):
            desplazamiento = (indice - (layer.repeat - 1) / 2) * layer.spread
            cuerpo = "".join(
                _primitive_svg(pieza, tamano, relleno, borde, layer.stroke_width, palette)
                for pieza in piezas
            )
            copias.append(
                f'<g transform="translate({_fmt(origen_x + desplazamiento - tamano / 2)}'
                f' {_fmt(origen_y - tamano / 2)})">{cuerpo}</g>'
            )
        contenido = "".join(copias)
        if giro:
            contenido = (
                f'<g transform="translate({_fmt(origen_x)} {_fmt(origen_y)}){giro}'
                f' translate({_fmt(-origen_x)} {_fmt(-origen_y)})">{contenido}</g>'
            )
        return f"<g{opacidad}>{contenido}</g>"

    if isinstance(layer, TextLayer):
        cuerpo = _text_svg(layer, palette)
        if layer.layout in (TextLayout.ARC, TextLayout.ARC_BELOW):
            # El texto curvo ya viene colocado en el lienzo por su camino.
            return f"<g{opacidad}>{cuerpo}</g>"
        transformacion = f"translate({_fmt(origen_x)} {_fmt(origen_y)}){giro}"
        return f'<g transform="{transformacion}"{opacidad}>{cuerpo}</g>'

    raise ValueError(f"capa desconocida: {layer!r}")


def _tree_transform(node: CompositionNode) -> str:
    """Transformación de un nodo contenedor alrededor de su ancla."""
    x, y = node.placement.origin()
    parts = [f"translate({_fmt(x)} {_fmt(y)})"]
    if node.placement.rotate:
        parts.append(f"rotate({_fmt(node.placement.rotate)})")
    if node.placement.scale != 1.0:
        parts.append(f"scale({_fmt(node.placement.scale)})")
    cx, cy = (50, 50) if node.transform_version == 2 else (x, y)
    parts.append(f"translate({_fmt(-cx)} {_fmt(-cy)})")
    return " ".join(parts)


def _node_svg(
    node: CompositionNode,
    palette: Palette,
    size: int,
    path: tuple[int, ...] = (),
) -> str:
    """Interpreta recursivamente la gramática de composición."""
    if size < node.min_size:
        return ""
    layer = node.as_layer()
    if layer is not None:
        return _layer_svg(layer, palette)

    children = sorted(enumerate(node.children), key=lambda item: item[1].z)
    opacity = f' opacity="{_fmt(node.opacity)}"' if node.opacity < 1 else ""
    transform = _tree_transform(node)

    if node.kind is NodeKind.REPEAT:
        child = node.children[0]
        copies: list[str] = []
        for index in range(node.count):
            offset = index - (node.count - 1) / 2
            dx, dy = offset * node.spread_x, offset * node.spread_y
            rotation = offset * node.rotate_step
            inner = _node_svg(child, palette, size, (*path, index))
            copies.append(
                f'<g transform="translate({_fmt(dx)} {_fmt(dy)}) rotate({_fmt(rotation)} 50 50)">'
                f"{inner}</g>"
            )
        return f'<g transform="{transform}"{opacity}>{"".join(copies)}</g>'

    content = "".join(_node_svg(child, palette, size, (*path, index)) for index, child in children)
    if node.kind is NodeKind.MASK:
        assert node.mask is not None
        identifier = "mask-" + ("-".join(map(str, path)) or "root")
        mask_color = "#000000" if node.mask_mode == "cutout" else "#FFFFFF"
        white = Palette(
            field=mask_color,
            mark=mask_color,
            ink=mask_color,
            accent=mask_color,
            paper=mask_color,
        )
        mask_svg = _node_svg(node.mask, white, size, (*path, 99))
        if node.mask_mode == "cutout":
            mask_svg = '<rect width="100" height="100" fill="#FFFFFF"/>' + mask_svg
        return (
            f'<mask id="{identifier}" maskUnits="userSpaceOnUse" x="0" y="0" width="100" height="100">{mask_svg}</mask>'
            f'<g transform="{transform}" mask="url(#{identifier})"{opacity}>{content}</g>'
        )
    return f'<g transform="{transform}"{opacity}>{content}</g>'


def render_svg(spec: LogoSpec, size: int = 128, title: str = "") -> str:
    """El logo como SVG, con el detalle que su tamaño permite.

    `size` no solo escala: **decide qué se dibuja**. Una capa con `min_size`
    por encima del tamaño pedido se omite, porque a 28 píxeles el nombre
    completo de un club es una mancha gris y el escudo se lee peor con él que
    sin él.
    """
    if spec.root is not None:
        capas = _node_svg(spec.root, spec.palette, size)
        # Un árbol compuesto sólo por detalle fino no debe producir una imagen
        # vacía. Las capas planas son la representación simplificada persistida
        # para miniaturas y compatibilidad.
        if not capas and spec.layers:
            capas = "".join(_layer_svg(capa, spec.palette) for capa in spec.ordered(size))
    else:
        capas = "".join(_layer_svg(capa, spec.palette) for capa in spec.ordered(size))
    etiqueta = f'role="img" aria-label="{escape(title)}"' if title else 'role="presentation"'
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_fmt(CANVAS)} {_fmt(CANVAS)}"'
        f' width="{size}" height="{size}" {etiqueta}>{capas}</svg>'
    )


def contact_sheet(specs: list[tuple[str, LogoSpec]], columns: int = 10, cell: int = 120) -> str:
    """Una hoja de contactos con muchos escudos, para mirarlos de un golpe.

    Es la prueba visual que un generador de identidades necesita y que ninguna
    aserción sustituye: cien escudos juntos enseñan en dos segundos si la
    paleta se repite, si los símbolos se parecen o si algo no se lee.
    """
    filas = math.ceil(len(specs) / columns)
    alto = filas * (cell + 22) + 10
    piezas: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{columns * cell}" height="{alto}"'
        f' viewBox="0 0 {columns * cell} {alto}">',
        f'<rect width="{columns * cell}" height="{alto}" fill="#12161b"/>',
    ]
    for indice, (nombre, spec) in enumerate(specs):
        columna, fila = indice % columns, indice // columns
        x, y = columna * cell + 10, fila * (cell + 22) + 10
        interior = (
            _node_svg(spec.root, spec.palette, cell - 20)
            if spec.root is not None
            else "".join(_layer_svg(capa, spec.palette) for capa in spec.ordered(cell - 20))
        )
        # Los identificadores deben ser únicos en todo el documento SVG,
        # incluso cuando cien marcas contienen el mismo arco tipográfico.
        interior = re.sub(
            r'(id="|href="#|url\(#)([^"\)]+)',
            lambda match, index=indice: f"{match[1]}sheet{index}-{match[2]}",
            interior,
        )
        piezas.append(
            f'<g transform="translate({x} {y}) scale({(cell - 20) / CANVAS})">{interior}</g>'
        )
        piezas.append(
            f'<text x="{x + (cell - 20) / 2}" y="{y + cell - 2}" fill="#8a96a3"'
            ' font-family="sans-serif" font-size="9" text-anchor="middle">'
            f"{escape(nombre[:22])}</text>"
        )
    piezas.append("</svg>")
    return "".join(piezas)
