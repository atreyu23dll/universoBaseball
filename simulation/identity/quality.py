"""Evaluación determinista de una marca antes de persistirla.

No intenta sustituir una revisión visual. Sí evita entregar defectos medibles:
contraste insuficiente, una miniatura vacía, elementos fuera del lienzo o un
símbolo que no pertenece al concepto declarado. Los resultados se guardan en
el sistema de identidad para que la selección sea explicable.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from simulation.identity.color import MIN_GRAPHIC_CONTRAST, MIN_TEXT_CONTRAST, contrast_ratio
from simulation.identity.geometry import area, intersect, union, visible_leaves
from simulation.identity.semantics import SPORT_MOTIFS, motifs_for
from simulation.identity.spec import LogoSpec, MotifLayer, PathLayer, ShapeLayer, TextLayer


@dataclass(frozen=True)
class LogoQuality:
    score: float
    contrast: float
    balance: float
    legibility: float
    complexity: float
    bounds: float
    semantic_coherence: float
    issues: tuple[str, ...]
    hierarchy: float = 1.0
    collisions: float = 1.0
    contour: float = 1.0
    symmetry: float = 1.0
    size_scores: tuple[tuple[int, float], ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "score": self.score,
            "hierarchy": self.hierarchy,
            "collisions": self.collisions,
            "contour": self.contour,
            "symmetry": self.symmetry,
            "size_scores": dict(self.size_scores),
            "contrast": self.contrast,
            "balance": self.balance,
            "legibility": self.legibility,
            "complexity": self.complexity,
            "bounds": self.bounds,
            "semantic_coherence": self.semantic_coherence,
            "issues": list(self.issues),
        }


def _extent(spec: LogoSpec) -> tuple[float, float, float, float]:
    """Incluye matrices anidadas, máscaras, grosor y copias."""
    return union([leaf.box for leaf in visible_leaves(spec)])


def structural_signature(spec: LogoSpec) -> str:
    """Firma de estructura; ignora colores para detectar recoloreos."""

    def structure(node):
        layer = node.as_layer()
        identity = node.kind.value
        if isinstance(layer, ShapeLayer):
            identity += ":" + layer.shape.value
        elif isinstance(layer, MotifLayer):
            identity += ":" + layer.motif
        elif isinstance(layer, PathLayer):
            identity += ":" + layer.role
            if layer.role == "symbol":
                identity += ":" + layer.label
            identity += ":" + ",".join(str(round(v / 5) * 5) for v in layer.bounds)
        elif isinstance(layer, TextLayer):
            identity += f":{layer.typography}:{layer.layout}"
        x, y = node.placement.origin()
        return [
            identity,
            round(x / 5),
            round(y / 5),
            round(node.placement.scale, 1),
            round(node.placement.rotate / 15),
            node.count,
            node.spread_x,
            node.spread_y,
            node.mask_mode,
            [structure(child) for child in node.children],
            structure(node.mask) if node.mask else None,
        ]

    from simulation.identity.spec import composition_from_layers

    return json.dumps(
        structure(spec.root or composition_from_layers(spec.layers)), separators=(",", ":")
    )


def exact_signature(spec: LogoSpec) -> str:
    from simulation.identity.render import render_svg

    # La igualdad es visual: la explicación no disimula dos dibujos idénticos.
    payload = render_svg(spec, size=256)
    return hashlib.sha256(payload.encode()).hexdigest()


def evaluate_logo(spec: LogoSpec, concept_family: str) -> LogoQuality:
    layers = spec.leaf_layers()
    issues: list[str] = []
    graphic_ratio = contrast_ratio(spec.palette.field_color, spec.palette.mark)
    text_ratio = contrast_ratio(spec.palette.field_color, spec.palette.accent)
    contrast = min(1.0, graphic_ratio / MIN_GRAPHIC_CONTRAST, text_ratio / MIN_TEXT_CONTRAST)
    if contrast < 1.0:
        issues.append("contraste insuficiente")

    left, top, right, bottom = _extent(spec)
    overflow = max(0.0, -left, -top, right - 100.0, bottom - 100.0)
    bounds = max(0.0, 1.0 - overflow / 35.0)
    if overflow > 1.0:
        issues.append("elementos fuera del lienzo")

    def identity_leaf(leaf):
        return isinstance(leaf.layer, (TextLayer, MotifLayer)) or (
            isinstance(leaf.layer, PathLayer) and leaf.layer.role in ("lettering", "symbol")
        )

    leaves = visible_leaves(spec)
    identities = [leaf for leaf in leaves if identity_leaf(leaf)]
    size_scores = []
    for size in (24, 48, 128, 256):
        small = [leaf for leaf in visible_leaves(spec, size) if identity_leaf(leaf)]
        dominant = max(
            (max(leaf.box[2] - leaf.box[0], leaf.box[3] - leaf.box[1]) for leaf in small), default=0
        )
        score_at_size = min(1.0, dominant / (55 if size < 64 else 35))
        if small and all(
            isinstance(leaf.layer, (PathLayer, TextLayer))
            and len(getattr(leaf.layer, "label", getattr(leaf.layer, "text", "")) or "") > 5
            and getattr(leaf.layer, "role", "lettering") == "lettering"
            for leaf in small
        ):
            score_at_size *= min(1, size / 96)
        size_scores.append((size, round(score_at_size, 3)))
    legibility = sum(score for _, score in size_scores) / 4
    if size_scores[0][1] < 0.7:
        issues.append("miniatura requiere variante reducida")
    count = len(leaves)
    complexity = max(0.25, 1 - abs(count - 5) / 30)
    total_area = sum(area(leaf.box) for leaf in identities) or 1
    center_x = (
        sum((leaf.box[0] + leaf.box[2]) / 2 * area(leaf.box) for leaf in identities) / total_area
    )
    center_y = (
        sum((leaf.box[1] + leaf.box[3]) / 2 * area(leaf.box) for leaf in identities) / total_area
    )
    balance = max(0, 1 - ((center_x - 50) ** 2 + (center_y - 50) ** 2) ** 0.5 / 60)
    # Detectar invasión de texto sobre símbolos; sus propias piezas y las
    # ligaduras sí se superponen intencionalmente.
    texts = [
        leaf
        for leaf in identities
        if isinstance(leaf.layer, TextLayer)
        or (
            isinstance(leaf.layer, PathLayer)
            and leaf.layer.role == "lettering"
            and len(leaf.layer.label) > 2
        )
    ]
    symbols = [
        leaf
        for leaf in identities
        if isinstance(leaf.layer, MotifLayer)
        or (isinstance(leaf.layer, PathLayer) and leaf.layer.role == "symbol")
    ]
    overlap = max(
        (area(intersect(t.box, s.box)) / max(1, area(t.box)) for t in texts for s in symbols),
        default=0,
    )
    collisions = max(0, 1 - overlap)
    if overlap > 0.35:
        issues.append("texto invade el símbolo")
    hierarchy = min(1, max((area(leaf.box) for leaf in identities), default=0) / 1000)
    contour = (
        1.0
        if all(
            not isinstance(leaf.layer, PathLayer)
            or leaf.layer.fill == "none"
            or "Z" in leaf.layer.d.upper()
            for leaf in identities
        )
        else 0.65
    )
    # Simetría de masas; no afirma simetría exacta de las curvas.
    symmetry = max(0, 1 - abs(center_x - 50) / 50)
    motifs = [layer.motif for layer in layers if isinstance(layer, MotifLayer)]
    motifs += list(
        {layer.label for layer in layers if isinstance(layer, PathLayer) and layer.role == "symbol"}
    )
    allowed = set(motifs_for(concept_family)) | set(SPORT_MOTIFS) | {"abstract"}
    semantic = 1.0 if not motifs or all(motif in allowed for motif in motifs) else 0.0
    if semantic == 0.0:
        issues.append("símbolo ajeno al concepto")

    score = (
        0.24 * contrast
        + 0.18 * balance
        + 0.20 * legibility
        + 0.10 * complexity
        + 0.16 * bounds
        + 0.12 * semantic
    )
    return LogoQuality(
        score=round(score * (0.9 + 0.1 * collisions), 4),
        hierarchy=round(hierarchy, 4),
        collisions=round(collisions, 4),
        contour=contour,
        symmetry=round(symmetry, 4),
        size_scores=tuple(size_scores),
        contrast=round(contrast, 4),
        balance=round(balance, 4),
        legibility=round(legibility, 4),
        complexity=round(complexity, 4),
        bounds=round(bounds, 4),
        semantic_coherence=round(semantic, 4),
        issues=tuple(issues),
    )


class LogoRegistry:
    """Evita duplicados exactos y demasiadas estructuras consecutivas."""

    def __init__(self) -> None:
        self._exact: set[str] = set()
        self._structures: dict[str, int] = {}

    def accepts(self, spec: LogoSpec) -> bool:
        exact = exact_signature(spec)
        structure = structural_signature(spec)
        return exact not in self._exact and self._structures.get(structure, 0) < 3

    def claim(self, spec: LogoSpec) -> None:
        exact = exact_signature(spec)
        structure = structural_signature(spec)
        self._exact.add(exact)
        self._structures[structure] = self._structures.get(structure, 0) + 1
