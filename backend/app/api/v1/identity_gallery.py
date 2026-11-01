"""Galería acotada y reproducible: no crea clubes ni escribe en sus identidades."""

import hashlib
from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query, Request, Response

from simulation.identity.demo import capability_examples, demo_manifest, demo_systems
from simulation.identity.profile import LOGO_VARIANTS
from simulation.identity.render import render_svg

router = APIRouter(prefix="/identity-gallery", tags=["identidades"])
Seed = Annotated[int, Query(ge=0, le=2**32 - 1)]
Index = Annotated[int, Path(ge=0, lt=100)]
Size = Annotated[int, Query(ge=16, le=1024)]
Variant = Literal["primary", "secondary", "monogram", "reduced", "cap", "light", "dark"]


def svg_response(svg: str, request: Request) -> Response:
    etag = '"' + hashlib.sha256(svg.encode()).hexdigest()[:24] + '"'
    headers = {
        "ETag": etag,
        "Cache-Control": "public, max-age=3600",
        "X-Content-Type-Options": "nosniff",
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(svg, media_type="image/svg+xml", headers=headers)


@router.get("")
def manifest(seed: Seed = 20261030):
    return demo_manifest(seed)


@router.get("/examples/{example}.svg")
def example_svg(
    example: Literal["monogram", "elephant", "roses"], request: Request, size: Size = 256
):
    spec = capability_examples()[example]
    return svg_response(render_svg(spec, size, title=spec.rationale), request)


@router.get("/{index}/crest.svg")
def gallery_svg(
    index: Index,
    request: Request,
    seed: Seed = 20261030,
    size: Size = 192,
    variant: Variant = "primary",
):
    identity = demo_systems(seed)[index]
    selected = "reduced" if size < 64 and variant == "primary" else variant
    return svg_response(
        render_svg(identity.logos[selected], size, identity.profile.naming.official_name), request
    )


@router.get("/{index}")
def identity_detail(index: Index, seed: Seed = 20261030):
    identity = demo_systems(seed)[index]
    return {"identity": identity.as_dict(), "variants": LOGO_VARIANTS}
