"""Contrato del logo: capas validadas, colocación y nivel de detalle.

Antes el logo viajaba como `list[dict[str, Any]]`. Eso significaba que un
motivo mal escrito no fallaba: llegaba al renderizador, no coincidía con
ninguna rama y **salía una estrella**. Nadie se enteraba, porque no había
contrato que violar.

Aquí el contrato existe: una unión discriminada por `kind`, con sus rangos, y
una versión de esquema. Un motivo inexistente falla al generarse, no al mirarse.

Tres cosas que el modelo añade y que la gramática anterior no podía expresar:

- **Colocación.** Cada capa tiene ancla, desplazamiento, escala y rotación, así
  que «tres rosas arriba» o «un triángulo transparente entre el cuadrado y el
  elefante» son descripciones que caben.
- **Orden explícito.** `z` decide qué tapa a qué, en vez del orden del array.
- **Nivel de detalle.** `min_size` dice a partir de qué tamaño en píxeles vale
  la pena dibujar una capa. Un wordmark de 12 unidades en un lienzo de 100
  mide 3,4 px dentro de un escudo de 28: a ese tamaño es una mancha, y lo
  honesto es no dibujarlo.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from simulation.identity.color import chroma_hue_of, lightness_of, oklch

#: El metal de una marca anterior a que el papel existiera. Sobrio a propósito:
#: ninguna capa vieja lo nombra, así que no aparece por sorpresa en un escudo
#: que ya estaba dibujado.
LEGACY_METAL = "#C9A227"

#: Versión del contrato. Cambia cuando cambia el **significado** de una capa, y
#: cada logo guardado recuerda con qué versión nació.
LOGO_SCHEMA_VERSION = 1

#: Lado del lienzo cuadrado en el que se componen todas las capas.
CANVAS = 100.0


class ColorRole(StrEnum):
    """Los ocho papeles de la paleta de un club.

    Son papeles, no colores: `field` es «el fondo del escudo» y `mark` «lo que
    se pinta encima». Que se lean entre sí es responsabilidad de la paleta, no
    de cada capa.

    Dos principales (`field`, `mark`), tres secundarios (`accent`, `shade`,
    `tint`) y tres terciarios (`ink`, `paper`, `metal`). Los tres últimos
    papeles nacieron después que el contrato: una marca guardada antes de que
    existieran los rellena al leerse, así que ningún escudo viejo deja de
    dibujarse.
    """

    FIELD = "field"
    MARK = "mark"
    INK = "ink"
    ACCENT = "accent"
    PAPER = "paper"
    SHADE = "shade"
    TINT = "tint"
    METAL = "metal"


class Anchor(StrEnum):
    CENTER = "center"
    TOP = "top"
    BOTTOM = "bottom"
    LEFT = "left"
    RIGHT = "right"
    TOP_LEFT = "top_left"
    TOP_RIGHT = "top_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_RIGHT = "bottom_right"


#: Coordenadas del ancla dentro del lienzo, en unidades de 0 a 100.
ANCHOR_POINT: dict[Anchor, tuple[float, float]] = {
    Anchor.CENTER: (50.0, 50.0),
    Anchor.TOP: (50.0, 26.0),
    Anchor.BOTTOM: (50.0, 74.0),
    Anchor.LEFT: (26.0, 50.0),
    Anchor.RIGHT: (74.0, 50.0),
    Anchor.TOP_LEFT: (30.0, 30.0),
    Anchor.TOP_RIGHT: (70.0, 30.0),
    Anchor.BOTTOM_LEFT: (30.0, 70.0),
    Anchor.BOTTOM_RIGHT: (70.0, 70.0),
}


class Shape(StrEnum):
    """Siluetas de soporte y de marco. Geometría, no dibujo."""

    SHIELD = "shield"
    CIRCLE = "circle"
    DIAMOND = "diamond"
    SQUARE = "square"
    HEXAGON = "hexagon"
    BANNER = "banner"
    TRIANGLE = "triangle"
    RING = "ring"
    ARCH = "arch"


class TextLayout(StrEnum):
    """Topología del texto: la forma en que las letras se colocan.

    No es solo la tipografía: `ARC` curva el nombre sobre el escudo, `STACKED`
    lo parte en líneas y `VERTICAL` lo pone en columna. Es lo que distingue un
    monograma de una marca verbal.
    """

    STRAIGHT = "straight"
    ARC = "arc"
    ARC_BELOW = "arc_below"
    STACKED = "stacked"
    VERTICAL = "vertical"


class Typography(StrEnum):
    BLOCK = "block"
    SLAB = "slab"
    SCRIPT = "script"
    CONDENSED = "condensed"
    GEOMETRIC = "geometric"


class NodeKind(StrEnum):
    """Nodos de la gramática gráfica.

    Las hojas (`shape`, `motif`, `text`) dibujan. Los demás describen cómo se
    compone el árbol: grupos/capas, transformaciones anidadas, repeticiones y
    máscaras. `ornament` es un grupo semántico que puede desaparecer en
    tamaños pequeños sin perder el símbolo principal.
    """

    GROUP = "group"
    LAYER = "layer"
    SHAPE = "shape"
    MOTIF = "motif"
    TEXT = "text"
    PATH = "path"
    MASK = "mask"
    REPEAT = "repeat"
    ORNAMENT = "ornament"


#: Un color de capa: un papel de la paleta, «none», o un color explícito. Lo
#: explícito existe porque una identidad puede pedir «tres rosas moradas» en un
#: club cuyo escudo no es morado, y un papel no sabría decirlo.
ColorRef = Annotated[
    str,
    Field(pattern=r"^(field|mark|ink|accent|paper|shade|tint|metal|none|#[0-9A-Fa-f]{6})$"),
]


class Placement(BaseModel):
    """Dónde, cuánto y con qué giro se dibuja una capa."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    anchor: Anchor = Anchor.CENTER
    #: Desplazamiento fino sobre el ancla, en unidades del lienzo.
    dx: float = Field(default=0.0, ge=-CANVAS, le=CANVAS)
    dy: float = Field(default=0.0, ge=-CANVAS, le=CANVAS)
    #: Tamaño de la capa como fracción del lienzo. 1.0 llena el escudo.
    scale: float = Field(default=1.0, gt=0.0, le=2.0)
    rotate: float = Field(default=0.0, ge=-180.0, le=180.0)

    def origin(self) -> tuple[float, float]:
        x, y = ANCHOR_POINT[self.anchor]
        return x + self.dx, y + self.dy


class LayerBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    #: Orden de pintado. Explícito a propósito: es lo que permite meter una
    #: capa **entre** otras dos sin reordenar la lista.
    z: int = Field(default=0, ge=-100, le=100)
    placement: Placement = Placement()
    fill: ColorRef = "mark"
    stroke: ColorRef = "none"
    stroke_width: float = Field(default=0.0, ge=0.0, le=12.0)
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    #: Píxeles mínimos del escudo para que esta capa se dibuje.
    min_size: int = Field(default=0, ge=0, le=512)


class ShapeLayer(LayerBase):
    """Una silueta: el soporte del escudo o un marco por encima."""

    kind: Literal["shape"] = "shape"
    shape: Shape


class MotifLayer(LayerBase):
    """Un símbolo paramétrico, opcionalmente repetido.

    `params` son los parámetros del motivo —cuántos pétalos, cuántas puntas—,
    no coordenadas: el dibujo lo construye el catálogo de motivos.
    """

    kind: Literal["motif"] = "motif"
    motif: str
    params: dict[str, float] = Field(default_factory=dict)
    repeat: int = Field(default=1, ge=1, le=7)
    #: Separación entre repeticiones, en unidades del lienzo.
    spread: float = Field(default=0.0, ge=0.0, le=CANVAS)

    @field_validator("motif")
    @classmethod
    def _motivo_conocido(cls, value: str) -> str:
        from simulation.identity.motifs import MOTIFS

        if value not in MOTIFS:
            raise ValueError(
                f"«{value}» no es un motivo del catálogo. Los conocidos: "
                f"{', '.join(sorted(MOTIFS))}"
            )
        return value


class TextLayer(LayerBase):
    """Letras: un monograma, unas iniciales o el nombre entero."""

    kind: Literal["text"] = "text"
    text: str = Field(min_length=1, max_length=40)
    layout: TextLayout = TextLayout.STRAIGHT
    typography: Typography = Typography.BLOCK
    #: Altura de las letras en unidades del lienzo.
    size: float = Field(default=28.0, gt=0.0, le=CANVAS)
    letter_spacing: float = Field(default=0.0, ge=-6.0, le=12.0)


class PathLayer(LayerBase):
    """Geometría calculada y congelada, en coordenadas del lienzo."""

    kind: Literal["path"] = "path"
    d: str = Field(
        min_length=1, max_length=150000, pattern=r"^[MmLlHhVvCcSsQqTtAaZz0-9eE., +\-\n]+$"
    )
    bounds: tuple[float, float, float, float] = (0, 0, 100, 100)
    role: Literal["symbol", "lettering", "ornament", "container"] = "symbol"
    label: str = ""


Layer = Annotated[ShapeLayer | MotifLayer | TextLayer | PathLayer, Field(discriminator="kind")]


class CompositionNode(BaseModel):
    """Un nodo del árbol de composición, independiente del SVG final.

    La representación es deliberadamente de dominio: dice «repite este
    símbolo», «recorta este grupo con esta forma» o «transforma estas capas».
    No guarda fragmentos de SVG. Así una variante puede regenerarse y otro
    intérprete futuro (por ejemplo Three.js) puede recorrer el mismo árbol.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: NodeKind
    name: str = Field(default="", max_length=48)
    z: int = Field(default=0, ge=-100, le=100)
    placement: Placement = Placement()
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    min_size: int = Field(default=0, ge=0, le=512)
    fill: ColorRef = "mark"
    stroke: ColorRef = "none"
    stroke_width: float = Field(default=0.0, ge=0.0, le=12.0)

    # Datos de las tres clases de hoja. El validador exige sólo los que
    # corresponden al `kind` y rechaza combinaciones ambiguas.
    shape: Shape | None = None
    d: str | None = Field(
        default=None, max_length=150000, pattern=r"^[MmLlHhVvCcSsQqTtAaZz0-9eE., +\-\n]+$"
    )
    bounds: tuple[float, float, float, float] = (0, 0, 100, 100)
    role: Literal["symbol", "lettering", "ornament", "container"] = "symbol"
    label: str = ""
    motif: str | None = None
    params: dict[str, float] = Field(default_factory=dict)
    text: str | None = Field(default=None, max_length=40)
    layout: TextLayout = TextLayout.STRAIGHT
    typography: Typography = Typography.BLOCK
    size: float = Field(default=28.0, gt=0.0, le=CANVAS)
    letter_spacing: float = Field(default=0.0, ge=-6.0, le=12.0)

    children: list[CompositionNode] = Field(default_factory=list, max_length=16)
    mask: CompositionNode | None = None
    mask_mode: Literal["intersect", "cutout"] = "intersect"
    # Version 1 conserva la interpretación de árboles ya persistidos.
    transform_version: Literal[1, 2] = 1
    count: int = Field(default=1, ge=1, le=12)
    spread_x: float = Field(default=0.0, ge=-CANVAS, le=CANVAS)
    spread_y: float = Field(default=0.0, ge=-CANVAS, le=CANVAS)
    rotate_step: float = Field(default=0.0, ge=-180.0, le=180.0)

    @model_validator(mode="after")
    def _estructura_valida(self) -> Self:
        leaf = self.kind in {NodeKind.SHAPE, NodeKind.MOTIF, NodeKind.TEXT, NodeKind.PATH}
        if self.kind is NodeKind.PATH and not self.d:
            raise ValueError("un nodo path necesita una trayectoria")
        if self.kind is NodeKind.SHAPE and self.shape is None:
            raise ValueError("un nodo shape necesita `shape`")
        if self.kind is NodeKind.MOTIF:
            from simulation.identity.motifs import MOTIFS

            if not self.motif or self.motif not in MOTIFS:
                raise ValueError(f"motivo de nodo desconocido: {self.motif!r}")
        if self.kind is NodeKind.TEXT and not self.text:
            raise ValueError("un nodo text necesita texto")
        if leaf and (self.children or self.mask is not None):
            raise ValueError("una hoja no puede contener otros nodos ni máscara")
        if self.kind in {NodeKind.GROUP, NodeKind.LAYER, NodeKind.ORNAMENT} and not self.children:
            raise ValueError(f"un nodo {self.kind} necesita hijos")
        if self.kind is NodeKind.REPEAT and len(self.children) != 1:
            raise ValueError("un nodo repeat contiene exactamente un hijo")
        if self.kind is NodeKind.MASK and (not self.children or self.mask is None):
            raise ValueError("un nodo mask necesita contenido y una máscara")
        return self

    def as_layer(self) -> Layer | None:
        """Convierte una hoja al contrato plano compatible."""
        common = {
            "z": self.z,
            "placement": self.placement,
            "fill": self.fill,
            "stroke": self.stroke,
            "stroke_width": self.stroke_width,
            "opacity": self.opacity,
            "min_size": self.min_size,
        }
        if self.kind is NodeKind.SHAPE:
            assert self.shape is not None
            return ShapeLayer(shape=self.shape, **common)
        if self.kind is NodeKind.PATH:
            return PathLayer(
                d=self.d, bounds=self.bounds, role=self.role, label=self.label, **common
            )
        if self.kind is NodeKind.MOTIF:
            assert self.motif is not None
            return MotifLayer(motif=self.motif, params=self.params, **common)
        if self.kind is NodeKind.TEXT:
            assert self.text is not None
            return TextLayer(
                text=self.text,
                layout=self.layout,
                typography=self.typography,
                size=self.size,
                letter_spacing=self.letter_spacing,
                **common,
            )
        return None


def node_from_layer(layer: Layer) -> CompositionNode:
    """Hoja arbórea equivalente a una capa del contrato anterior."""
    data: dict[str, Any] = {
        "kind": layer.kind,
        "z": layer.z,
        "placement": layer.placement,
        "fill": layer.fill,
        "stroke": layer.stroke,
        "stroke_width": layer.stroke_width,
        "opacity": layer.opacity,
        "min_size": layer.min_size,
    }
    if isinstance(layer, ShapeLayer):
        data["shape"] = layer.shape
    elif isinstance(layer, PathLayer):
        data.update(d=layer.d, bounds=layer.bounds, role=layer.role, label=layer.label)
    elif isinstance(layer, MotifLayer):
        data.update(motif=layer.motif, params=layer.params)
    else:
        data.update(
            text=layer.text,
            layout=layer.layout,
            typography=layer.typography,
            size=layer.size,
            letter_spacing=layer.letter_spacing,
        )
    return CompositionNode.model_validate(data)


def composition_from_layers(layers: list[Layer], *, name: str = "marca") -> CompositionNode:
    """Agrupa capas existentes en un árbol versionable."""
    return CompositionNode(
        kind=NodeKind.GROUP,
        name=name,
        children=[node_from_layer(layer) for layer in sorted(layers, key=lambda item: item.z)],
    )


class Palette(BaseModel):
    """Los ocho colores de un club, con su contraste ya comprobado.

    Dos principales, tres secundarios y tres terciarios. El reparto no es
    decorativo: un escudo necesita margen para separar, perfilar y rematar sin
    salirse de la familia del club.
    """

    # `field` es palabra reservada de Pydantic como nombre de campo, así que el
    # atributo se llama `field_color` y el JSON sigue diciendo `field`: el
    # contrato que ve la interfaz no se dobla por un detalle de Python.
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    field_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$", alias="field")
    mark: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    ink: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    accent: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    paper: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    shade: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    tint: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    metal: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")

    @model_validator(mode="before")
    @classmethod
    def _completar_papeles_nuevos(cls, data: Any) -> Any:
        """Una paleta guardada con cinco colores sigue siendo válida.

        Los tres papeles nuevos se derivan del campo con la misma aritmética
        que usaba el blasón antes de que existieran —un tono más claro y otro
        más oscuro— y el metal cae en un oro sobrio. Así una marca anterior al
        contrato se sigue dibujando con el mismo repertorio de tinturas que
        tenía, en vez de quedarse con tres colores repetidos.
        """
        if not isinstance(data, dict):
            return data
        campo = data.get("field", data.get("field_color"))
        if not isinstance(campo, str) or not campo.startswith("#"):
            return data
        croma, tono = chroma_hue_of(campo)
        luz = lightness_of(campo)
        data.setdefault("shade", oklch(max(0.12, luz - 0.16), croma * 1.05, tono))
        data.setdefault("tint", oklch(min(0.9, luz + 0.19), croma, tono))
        data.setdefault("metal", LEGACY_METAL)
        return data

    def resolve(self, ref: str) -> str:
        """El color de una referencia de capa. `none` significa sin relleno."""
        if ref == "none":
            return "none"
        if ref.startswith("#"):
            return ref
        return {
            ColorRole.FIELD: self.field_color,
            ColorRole.MARK: self.mark,
            ColorRole.INK: self.ink,
            ColorRole.ACCENT: self.accent,
            ColorRole.PAPER: self.paper,
            ColorRole.SHADE: self.shade,
            ColorRole.TINT: self.tint,
            ColorRole.METAL: self.metal,
        }[ColorRole(ref)]


class LogoSpec(BaseModel):
    """Un logo completo: paleta, capas y por qué es así.

    `rationale` no es decoración: es la traza de qué decidió esta identidad —el
    lugar, el concepto del nombre, la personalidad de quien manda— y sin ella
    un logo generado es indistinguible de uno aleatorio.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    design_style: str = "legacy"
    schema_version: int = LOGO_SCHEMA_VERSION
    variant: str = Field(default="primary", pattern=r"^[a-z][a-z0-9_-]{0,31}$")
    palette: Palette
    # `layers` mantiene dibujables las marcas de schema v1. Las nuevas llevan
    # también `root`, que es la fuente estructurada para composición avanzada.
    layers: list[Layer] = Field(default_factory=list, max_length=12)
    root: CompositionNode | None = None
    rationale: str = ""

    @model_validator(mode="after")
    def _version_conocida(self) -> Self:
        if self.schema_version != LOGO_SCHEMA_VERSION:
            raise ValueError(
                f"logo de versión {self.schema_version}; este código entiende la "
                f"{LOGO_SCHEMA_VERSION}. Migrar antes de dibujarlo, no adivinar"
            )
        if not self.layers and self.root is None:
            raise ValueError("un logo necesita capas o un árbol de composición")
        return self

    def leaf_layers(self) -> list[Layer]:
        """Hojas del árbol como capas, para análisis y compatibilidad."""
        if self.layers:
            return list(self.layers)
        assert self.root is not None
        leaves: list[Layer] = []

        def visit(node: CompositionNode) -> None:
            layer = node.as_layer()
            if layer is not None:
                leaves.append(layer)
            for child in node.children:
                visit(child)

        visit(self.root)
        return leaves

    def ordered(self, size: int | None = None) -> list[Layer]:
        """Las capas en orden de pintado, filtradas por tamaño.

        El filtro es el nivel de detalle: a 28 píxeles un escudo no puede
        mostrar el nombre completo, y dibujarlo de todos modos produce una
        mancha gris que empeora la marca en vez de enriquecerla.
        """
        layers = self.leaf_layers()
        visibles = [capa for capa in layers if size is None or size >= capa.min_size]
        if not visibles:
            # Nunca se devuelve un logo vacío. Lo que se rescata es el dibujo:
            # a este tamaño una palabra es una mancha, pero una figura todavía
            # se reconoce. Un logo hecho solo de letras se dibuja entero.
            visibles = [capa for capa in layers if not isinstance(capa, TextLayer)]
            visibles = visibles or layers
        return sorted(visibles, key=lambda capa: capa.z)

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", by_alias=True)
