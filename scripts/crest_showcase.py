"""Comparación reproducible de firmas, fondos y miniaturas: python scripts/crest_showcase.py."""

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from simulation.generation.naming import ClubName
from simulation.identity.art_direction import STYLES, compose_identity_logo
from simulation.identity.profile import _coordinated_variants
from simulation.identity.render import render_svg


def main():
    samples = [
        ("Ciudad Juárez", "Diablos"),
        ("Monterrey", "Sierra"),
        ("Chihuahua", "Nopaleras"),
        ("São Paulo", "Raízes"),
        ("La Habana", "Furia"),
    ]
    svg = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="650" viewBox="0 0 1200 650">'
    ]
    svg.append('<rect width="1200" height="650" fill="#eee9dd"/>')
    svg.append('<rect y="320" width="1200" height="330" fill="#111a24"/>')
    for index, (style, (place, name)) in enumerate(zip(STYLES, samples, strict=True)):
        primary = compose_identity_logo(
            random.Random(index + 5),
            place_name=place,
            nickname=name,
            short_name=name,
            concept_family="community",
            ambition=0.6,
            risk_tolerance=0.4,
            community_reach=0.8,
            design_style=style,
        )
        verbal = ClubName(
            full=f"{name} de {place}",
            nickname=name,
            short=name,
            family="community",
            initials="",
            concept=name,
        )
        variants = _coordinated_variants(primary, verbal, index, place)
        for row, variant in enumerate(("light", "dark")):
            x, y = index * 240, row * 320
            svg.append(f'<g transform="translate({x + 12} {y + 12})">')
            svg.append(render_svg(variants[variant], 216))
            svg.append("</g>")
            for offset, size in ((56, 24), (103, 40), (164, 56)):
                svg.append(f'<g transform="translate({x + offset} {y + 240})">')
                svg.append(render_svg(variants["reduced"], size))
                svg.append("</g>")
    svg.append("</svg>")
    path = Path("crests-review.svg")
    path.write_text("".join(svg), encoding="utf-8")
    print(path.resolve())


if __name__ == "__main__":
    main()
