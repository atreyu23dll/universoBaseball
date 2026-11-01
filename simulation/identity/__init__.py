"""Identidad generativa de un club: nombre, paleta y logo por capas.

El orden de lectura es el de sus dependencias:

- `color`: OKLCH y contraste WCAG. Es la base, porque sin contraste exigido un
  generador de escudos produce manchas.
- `spec`: el contrato del logo —capas validadas, colocación, nivel de detalle—.
- `motifs`: los símbolos, como funciones paramétricas en una caja normalizada.
- `semantics`: qué símbolos pertenecen a qué concepto del nombre.
- `palette`: los cinco papeles de color de un club, ya legibles entre sí.
- `compose`: la gramática que decide qué capas tiene este club y por qué.
- `render`: el **único** intérprete, de especificación a SVG.
"""

from simulation.identity.color import (
    MIN_GRAPHIC_CONTRAST,
    MIN_TEXT_CONTRAST,
    contrast_ratio,
    ensure_contrast,
    oklch,
)
from simulation.identity.compose import compose_logo, place_initials
from simulation.identity.motifs import MOTIFS, primitives_for
from simulation.identity.palette import palette_for
from simulation.identity.profile import (
    IDENTITY_GENERATOR_VERSION,
    IDENTITY_SCHEMA_VERSION,
    LOGO_VARIANTS,
    IdentityProfile,
    IdentitySystem,
    build_identity_system,
    redesign_identity_system,
)
from simulation.identity.quality import (
    LogoQuality,
    LogoRegistry,
    evaluate_logo,
    structural_signature,
)
from simulation.identity.render import contact_sheet, render_svg
from simulation.identity.semantics import FAMILY_MOTIFS, SPORT_MOTIFS, motifs_for
from simulation.identity.spec import (
    CANVAS,
    LOGO_SCHEMA_VERSION,
    Anchor,
    ColorRole,
    CompositionNode,
    Layer,
    LogoSpec,
    MotifLayer,
    NodeKind,
    Palette,
    PathLayer,
    Placement,
    Shape,
    ShapeLayer,
    TextLayer,
    TextLayout,
    Typography,
    composition_from_layers,
)

__all__ = [
    "CANVAS",
    "FAMILY_MOTIFS",
    "IDENTITY_GENERATOR_VERSION",
    "IDENTITY_SCHEMA_VERSION",
    "LOGO_SCHEMA_VERSION",
    "LOGO_VARIANTS",
    "MIN_GRAPHIC_CONTRAST",
    "MIN_TEXT_CONTRAST",
    "MOTIFS",
    "SPORT_MOTIFS",
    "Anchor",
    "ColorRole",
    "CompositionNode",
    "IdentityProfile",
    "IdentitySystem",
    "Layer",
    "LogoQuality",
    "LogoRegistry",
    "LogoSpec",
    "MotifLayer",
    "NodeKind",
    "Palette",
    "PathLayer",
    "Placement",
    "Shape",
    "ShapeLayer",
    "TextLayer",
    "TextLayout",
    "Typography",
    "build_identity_system",
    "compose_logo",
    "composition_from_layers",
    "contact_sheet",
    "contrast_ratio",
    "ensure_contrast",
    "evaluate_logo",
    "motifs_for",
    "oklch",
    "palette_for",
    "place_initials",
    "primitives_for",
    "redesign_identity_system",
    "render_svg",
    "structural_signature",
]
