"""Cajas de lo que dibuja el árbol: matrices anidadas, máscaras y repeticiones."""

from __future__ import annotations

import math
from dataclasses import dataclass

from simulation.identity.spec import (
    CompositionNode,
    Layer,
    LogoSpec,
    MotifLayer,
    NodeKind,
    PathLayer,
    ShapeLayer,
)

IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def multiply(a, b):
    aa, ab, ac, ad, ae, af = a
    ba, bb, bc, bd, be, bf = b
    return (
        aa * ba + ac * bb,
        ab * ba + ad * bb,
        aa * bc + ac * bd,
        ab * bc + ad * bd,
        aa * be + ac * bf + ae,
        ab * be + ad * bf + af,
    )


def transform(x=0, y=0, scale=1, angle=0, cx=0, cy=0):
    c, s = math.cos(math.radians(angle)) * scale, math.sin(math.radians(angle)) * scale
    return (c, s, -s, c, x - c * cx + s * cy, y - s * cx - c * cy)


def box_transform(box, matrix):
    a, b, c, d, e, f = matrix
    left, top, right, bottom = box
    points = [
        (a * x + c * y + e, b * x + d * y + f)
        for x, y in ((left, top), (right, top), (left, bottom), (right, bottom))
    ]
    return (
        min(x for x, y in points),
        min(y for x, y in points),
        max(x for x, y in points),
        max(y for x, y in points),
    )


def intersect(a, b):
    left, top, right, bottom = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    return (left, top, max(left, right), max(top, bottom))


def union(boxes):
    return (
        (
            min(b[0] for b in boxes),
            min(b[1] for b in boxes),
            max(b[2] for b in boxes),
            max(b[3] for b in boxes),
        )
        if boxes
        else (50, 50, 50, 50)
    )


def area(box):
    return max(0, box[2] - box[0]) * max(0, box[3] - box[1])


@dataclass(frozen=True)
class VisibleLeaf:
    layer: Layer
    box: tuple[float, float, float, float]
    owner: str


def visible_leaves(spec: LogoSpec, size=512) -> list[VisibleLeaf]:
    result = []

    def visit(node: CompositionNode, matrix=IDENTITY, clip=None, owner="", path="root", depth=0):
        if depth > 32:
            raise ValueError("árbol de identidad demasiado profundo")
        if node.min_size > size or node.opacity == 0:
            return
        layer = node.as_layer()
        if layer is not None:
            x, y = layer.placement.origin()
            local = transform(x, y, layer.placement.scale, layer.placement.rotate, 50, 50)
            if isinstance(layer, PathLayer):
                box = layer.bounds
            elif isinstance(layer, ShapeLayer):
                box = (0, 0, 100, 100)
            elif isinstance(layer, MotifLayer):
                extra = layer.spread * (layer.repeat - 1) / 2
                box = (25 - extra, 25, 75 + extra, 75)
            else:
                half = min(48, len(layer.text) * layer.size * 0.34)
                height = layer.size * (
                    len(layer.text) / 2 if layer.layout.value == "vertical" else 0.75
                )
                box = (50 - half, 50 - height, 50 + half, 50 + height)
            stroke = layer.stroke_width / 2 if layer.stroke != "none" else 0
            box = (box[0] - stroke, box[1] - stroke, box[2] + stroke, box[3] + stroke)
            box = box_transform(box, multiply(matrix, local))
            if clip is not None:
                box = intersect(box, clip)
            if area(box) > 0:
                result.append(VisibleLeaf(layer, box, owner or path))
            return
        x, y = node.placement.origin()
        cx, cy = (50, 50) if node.transform_version == 2 else (x, y)
        matrix = multiply(
            matrix, transform(x, y, node.placement.scale, node.placement.rotate, cx, cy)
        )
        if node.name.startswith("symbol:"):
            owner = path
        if node.kind is NodeKind.MASK and node.mask_mode == "intersect":
            before = len(result)
            visit(node.mask, matrix, clip, path=path + "/mask", depth=depth + 1)
            masks = result[before:]
            del result[before:]
            mask_box = union([leaf.box for leaf in masks])
            clip = intersect(clip, mask_box) if clip else mask_box
        for index, child in enumerate(node.children):
            if node.kind is NodeKind.REPEAT:
                for copy in range(node.count):
                    offset = copy - (node.count - 1) / 2
                    repeated = multiply(
                        matrix,
                        transform(
                            50 + offset * node.spread_x,
                            50 + offset * node.spread_y,
                            angle=offset * node.rotate_step,
                            cx=50,
                            cy=50,
                        ),
                    )
                    visit(child, repeated, clip, owner, path + f"/{index}:{copy}", depth + 1)
            else:
                visit(child, matrix, clip, owner, path + f"/{index}", depth + 1)

    if spec.root:
        visit(spec.root)
    else:
        from simulation.identity.spec import node_from_layer

        for index, layer in enumerate(spec.layers):
            visit(node_from_layer(layer), path=str(index))
    return result
