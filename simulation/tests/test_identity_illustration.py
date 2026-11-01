import random
import xml.etree.ElementTree as ET

from simulation.identity.art_direction import compose_identity_logo
from simulation.identity.motifs import primitives_for
from simulation.identity.render import contact_sheet, render_svg


def test_illustration_is_opt_in_and_has_contrasting_details():
    for motif in ("rose", "bird", "elephant", "summit", "ball", "bull", "oak", "cactus"):
        old = primitives_for(motif)
        new = primitives_for(motif, {"illustration_version": 1})
        assert old != new
        assert any(p["kind"] == "path" for p in new)
        assert len({p["color"] for p in new}) >= 2
        assert old == primitives_for(motif, {"illustration_version": 0})


def test_new_compositions_render_reproducibly_and_sheet_ids_are_unique():
    def make(seed):
        return compose_identity_logo(
            random.Random(seed),
            place_name="Ciudad Juárez",
            nickname="Unión",
            short_name="Unión Juárez",
            concept_family="nature",
            ambition=0.5,
            risk_tolerance=0.5,
            community_reach=0.7,
        )

    specs = [("Club", make(seed)) for seed in range(30)]
    for seed, (_, spec) in enumerate(specs):
        assert spec == make(seed)
        for size in (24, 128, 512):
            ET.fromstring(render_svg(spec, size=size))
    root = ET.fromstring(contact_sheet(specs))
    ids = [element.attrib["id"] for element in root.iter() if "id" in element.attrib]
    assert len(ids) == len(set(ids))
