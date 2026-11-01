"""Perfil institucional persistente y sistema coordinado de marcas.

El perfil se crea antes que sus logos y es la fuente común del nombre, los
símbolos y las variantes. Distingue datos territoriales/institucionales que
vienen de una fuente de las decisiones creativas del simulador: una referencia
cultural ausente se declara ausente; no se rellena con folclore inventado.
"""

from __future__ import annotations

import random
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from simulation.core.rng import derive_seed
from simulation.generation.naming import ClubName
from simulation.generation.organization import OrganizationProfile
from simulation.identity.art_direction import (
    STYLES,
    compose_identity_logo,
    make_spec,
    text_or_outline,
)
from simulation.identity.compose import place_initials
from simulation.identity.grammar import GRAPHIC_STYLES, symbol_variants
from simulation.identity.lettering import monogram, supported
from simulation.identity.palette import club_palette
from simulation.identity.quality import LogoQuality, LogoRegistry, evaluate_logo
from simulation.identity.semantics import coherent, drawable, motifs_for, symbol_for_concept
from simulation.identity.spec import (
    LogoSpec,
    MotifLayer,
    Placement,
    Shape,
    ShapeLayer,
    TextLayer,
    Typography,
    composition_from_layers,
)
from simulation.identity.symbols import SYMBOL_GENERATORS

IDENTITY_SCHEMA_VERSION = 1
IDENTITY_GENERATOR_VERSION = "identity/7.0.0"
LOGO_VARIANTS = ("primary", "secondary", "monogram", "reduced", "cap", "light", "dark")


class ReferenceStatus(StrEnum):
    VERIFIED = "verified"
    DOCUMENTED_INSTITUTION = "documented_institution"
    GENERATED = "generated"
    UNAVAILABLE = "unavailable"


class IdentityReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str
    value: str
    status: ReferenceStatus
    source: str
    note: str = ""


class NamingProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    official_name: str
    short_name: str
    initials: str
    nickname: str | None = None
    sporting_demonym: str | None = None
    grammar: str
    concept_family: str
    concept: str
    candidates_considered: int = Field(ge=1)
    rationale: str
    #: La veta que motivó el nombre: `territorio`, `epoca` o `patronazgo`.
    motivation: str = ""
    #: El hecho del club del que salió el nombre, en una frase.
    story: str = ""
    #: Cómo se acuñó la palabra: «mezquite + -al». Vacío si se usó un lema.
    formation: str = ""
    #: Clave de la raíz léxica, para medir repetición entre clubes.
    root: str = ""


class Swatch(BaseModel):
    """Un color del club con su oficio: qué es y para qué sirve."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: str
    hex: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    name: str
    use: str


class ClubColors(BaseModel):
    """La paleta del club agrupada como se usa: 2 + 3 + 3.

    Dos principales —los de la camiseta—, tres secundarios que dan aire al
    diseño y tres terciarios de oficio. Es lo que le da margen a un escudo para
    separar, perfilar y rematar sin salirse de la familia del club.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    scheme: str
    metal: str
    primary: list[Swatch] = Field(min_length=2, max_length=2)
    secondary: list[Swatch] = Field(min_length=3, max_length=3)
    tertiary: list[Swatch] = Field(min_length=3, max_length=3)
    rationale: str


class VisualLanguage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol_family: str
    preferred_symbols: list[str]
    geometry: str
    container_policy: str
    symmetry: str
    typography: Typography
    complexity_target: str
    color_principle: str


class IdentityProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = IDENTITY_SCHEMA_VERSION
    generator_version: str = IDENTITY_GENERATOR_VERSION
    seed: int = Field(ge=0)
    institution_type: str
    sports_identity_status: str
    territory: dict[str, str]
    foundation_year: int
    foundation_context: str
    values: dict[str, float]
    references: list[IdentityReference]
    naming: NamingProfile
    visual_language: VisualLanguage
    #: Opcional porque hay perfiles guardados antes de que la paleta del club
    #: fuera un artefacto propio; los nuevos la traen siempre.
    palette: ClubColors | None = None
    rationale: str


class IdentitySystem(BaseModel):
    """Artefacto persistido: perfil, variantes y control de calidad."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = IDENTITY_SCHEMA_VERSION
    generator_version: str = IDENTITY_GENERATOR_VERSION
    seed: int = Field(ge=0)
    revision: int = Field(default=1, ge=1)
    revision_reason: str = "foundation"
    # Revisiones completas anteriores. Un rediseño explícito añade aquí el
    # artefacto viejo; actualizar el algoritmo por sí solo no toca este campo.
    history: list[dict[str, Any]] = Field(default_factory=list)
    profile: IdentityProfile
    logos: dict[str, LogoSpec]
    quality: dict[str, dict[str, object]]

    @model_validator(mode="after")
    def _variantes_completas(self) -> Self:
        missing = set(LOGO_VARIANTS) - set(self.logos)
        if missing:
            raise ValueError(f"faltan variantes de marca: {', '.join(sorted(missing))}")
        return self

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", by_alias=True)


def _foundation_context(organization: OrganizationProfile, place_name: str) -> str:
    governance = str(organization.governance)
    motive = {
        "collective": "un grupo vecinal quiso sostener un espacio compartido de juego",
        "members_assembly": "sus primeros socios formalizaron una asociación local",
        "family_private": "una familia organizó y sostuvo el club",
        "business_backed": "un negocio local respaldó la nueva organización",
        "school_program": "una institución educativa abrió un programa deportivo",
        "municipal_program": "el municipio impulsó un programa deportivo comunitario",
        "foundation": "una fundación articuló el proyecto deportivo",
        "sports_company": "una sociedad deportiva constituyó el club",
        "franchise": "una organización promotora estableció una franquicia",
    }.get(governance, "sus fundadores organizaron una institución deportiva")
    return f"En la ficción de la simulación, en {place_name}, {motive}."


def _primary_typography(spec: LogoSpec, seed: int) -> Typography:
    if spec.design_style != "legacy":
        return (
            Typography.SLAB
            if spec.design_style in ("heritage", "seal", "ligature")
            else Typography.BLOCK
        )
    for layer in spec.leaf_layers():
        if isinstance(layer, TextLayer):
            return layer.typography
    return random.Random(derive_seed(seed, "typography")).choice(list(Typography))


def _primary_motif(spec: LogoSpec) -> MotifLayer:
    for layer in spec.leaf_layers():
        if isinstance(layer, MotifLayer):
            return layer
    raise ValueError("la marca principal no contiene símbolo")


def _variant(
    primary: LogoSpec,
    variant: str,
    layers: list[ShapeLayer | MotifLayer | TextLayer],
    rationale: str,
) -> LogoSpec:
    return LogoSpec(
        variant=variant,
        palette=primary.palette,
        layers=layers,  # type: ignore[arg-type]
        root=composition_from_layers(layers, name=f"variante {variant}"),  # type: ignore[arg-type]
        rationale=rationale,
    )


def _coordinated_variants(
    primary: LogoSpec,
    verbal: ClubName,
    identity_seed: int,
    place_name: str,
) -> dict[str, LogoSpec]:
    if primary.design_style != "legacy":
        initials = place_initials(place_name)[:2]
        variants = {"primary": primary}
        for name, box in (
            ("monogram", (22, 16, 78, 82)),
            ("reduced", (18, 12, 82, 88)),
            ("cap", (24, 18, 76, 80)),
        ):
            layers = monogram(initials, box=box, fill="field")
            if not layers:
                layers = [text_or_outline(initials, box=box, fill="field", stroke="paper")]
            layers = [
                layer.model_copy(update={"stroke": "paper", "stroke_width": 2.5})
                for layer in layers
            ]
            if name == "reduced":
                # Una sola pasada: la marca reducida es la que se sirve por
                # debajo de 64 píxeles, y tiene que dibujar **menos** que la
                # principal, no el doble. Dos pasadas de contorno a ese tamaño
                # son una mancha, además de más elementos que el original.
                layers = [
                    layer.model_copy(
                        update={"fill": "mark", "stroke": "paper", "stroke_width": 5.0, "z": 0}
                    )
                    for layer in layers
                ]
            variants[name] = make_spec(
                primary.palette,
                layers,
                primary.design_style,
                "Monograma coordinado para " + name,
                name,
            )
        if primary.design_style in GRAPHIC_STYLES:
            # Conservar el árbol: un escudo complejo no cabe necesariamente
            # en las 12 capas del contrato plano de las marcas antiguas.
            variants.update(symbol_variants(primary))
            return variants
        layers = [layer for layer in primary.leaf_layers() if layer.min_size == 0]
        variants["secondary"] = make_spec(
            primary.palette,
            layers,
            primary.design_style,
            "Firma sin detalles de tamaño grande.",
            "secondary",
        )
        variants["light"] = primary.model_copy(update={"variant": "light"})
        if primary.design_style in ("heritage", "athletic", "ligature"):
            dark_layers = [
                layer.model_copy(
                    update={
                        "fill": "mark" if layer.fill == "field" else layer.fill,
                        "stroke": "field" if layer.stroke == "paper" else layer.stroke,
                    }
                )
                for layer in primary.leaf_layers()
            ]
            variants["dark"] = make_spec(
                primary.palette,
                dark_layers,
                primary.design_style,
                "Firma clara para fondo oscuro.",
                "dark",
            )
        else:
            variants["dark"] = primary.model_copy(update={"variant": "dark"})
        return variants
    motif = _primary_motif(primary)
    typography = _primary_typography(primary, identity_seed)
    initials = verbal.initials or place_initials(verbal.short or verbal.full)
    rng = random.Random(derive_seed(identity_seed, "variants"))

    symbol = MotifLayer(
        z=2,
        motif=motif.motif,
        params=motif.params,
        fill="mark",
        stroke=motif.stroke,
        stroke_width=motif.stroke_width,
        placement=Placement(scale=0.72),
    )
    secondary_layers: list[ShapeLayer | MotifLayer | TextLayer] = [symbol]
    if rng.random() < 0.55:
        secondary_layers.insert(
            0,
            ShapeLayer(
                z=0,
                shape=rng.choice((Shape.CIRCLE, Shape.DIAMOND, Shape.HEXAGON)),
                fill="field",
                stroke="ink",
                stroke_width=2.5,
            ),
        )

    monogram_text = TextLayer(
        z=2,
        text=initials,
        typography=typography,
        size=42 if len(initials) <= 2 else 34,
        fill="accent",
        stroke="ink",
        stroke_width=2.0,
    )
    monogram_layers: list[ShapeLayer | MotifLayer | TextLayer] = [monogram_text]
    if rng.random() < 0.7:
        monogram_layers.insert(
            0,
            ShapeLayer(z=0, shape=Shape.CIRCLE, fill="field", stroke="ink", stroke_width=3),
        )

    cap_layers: list[ShapeLayer | MotifLayer | TextLayer] = [
        ShapeLayer(
            z=0,
            shape=rng.choice((Shape.DIAMOND, Shape.HEXAGON, Shape.CIRCLE)),
            fill="field",
            stroke="ink",
            stroke_width=3,
            placement=Placement(scale=0.92),
        ),
        monogram_text.model_copy(update={"z": 2, "placement": Placement(scale=0.88)}),
    ]
    reduced = _variant(
        primary,
        "reduced",
        [symbol.model_copy(update={"placement": Placement(scale=0.86)})],
        "Símbolo aislado para tamaños mínimos; conserva el concepto de la marca principal.",
    )
    variants = {
        "primary": primary.model_copy(update={"variant": "primary"}),
        "secondary": _variant(
            primary,
            "secondary",
            secondary_layers,
            "Firma secundaria: el mismo símbolo con una estructura más compacta.",
        ),
        "monogram": _variant(
            primary,
            "monogram",
            monogram_layers,
            f"Monograma «{initials}» derivado de la identidad verbal.",
        ),
        "reduced": reduced,
        "cap": _variant(
            primary,
            "cap",
            cap_layers,
            "Emblema de gorra: iniciales legibles y contorno cerrado para bordado.",
        ),
        # Las versiones de fondo conservan una marca autocontenida con
        # contraste ya reparado. No invierten colores a ciegas: eso rompería la
        # relación field/mark medida por la paleta.
        "light": primary.model_copy(
            update={
                "variant": "light",
                "rationale": primary.rationale + " Variante para fondo claro.",
            }
        ),
        "dark": primary.model_copy(
            update={
                "variant": "dark",
                "rationale": primary.rationale + " Variante para fondo oscuro.",
            }
        ),
    }
    return variants


def build_identity_system(
    *,
    identity_seed: int,
    verbal: ClubName,
    place_name: str,
    country_code: str,
    institution_type: str,
    foundation_year: int,
    organization: OrganizationProfile,
    territory_confidence: str,
    real_institution: dict[str, str] | None = None,
    logo_registry: LogoRegistry | None = None,
) -> IdentitySystem:
    """Genera perfil y variantes con subsemillas estables."""
    # El perfil fija intención verbal y visual antes de dibujar una candidata.
    # El motivo declarado por la raíz del nombre manda: lo decidió el mismo
    # inventario que acuñó la palabra, y no depende de reconocer su ortografía.
    declarado = drawable(getattr(verbal, "motif", ""))
    symbol = (
        declarado
        if declarado in SYMBOL_GENERATORS and coherent(declarado, verbal.family)
        else symbol_for_concept(verbal.concept or verbal.nickname, verbal.family)
    )
    if symbol not in SYMBOL_GENERATORS:
        # El catálogo gráfico manda sobre el inventario léxico: lo que no tiene
        # contorno se dibuja como marca abstracta, no se deja fallar.
        symbol = "abstract"
    direction_rng = random.Random(derive_seed(identity_seed, "direction"))
    # Sin objeto literal, elegir entre metáforas de la familia del nombre.
    # La pelota deja de ocupar el 40% de estas identidades por defecto.
    if symbol == "abstract":
        symbol_rng = random.Random(derive_seed(identity_seed, "family-symbol"))
        repertoire = [name for name in motifs_for(verbal.family) if name in SYMBOL_GENERATORS]
        symbol = symbol_rng.choices(
            [*repertoire, "abstract", "ball"],
            weights=[0.35 if name in {"sun", "summit"} else 1.0 for name in repertoire]
            + [0.5, 0.15],
            k=1,
        )[0]
    # La familia rotulada dibuja el nombre con **contornos propios**. Si el
    # alfabeto del club no está en esa fuente —japonés, coreano, árabe—, lo que
    # sale no es una marca rotulada: es texto del sistema estirado, y depende de
    # las fuentes que tenga quien mire. En ese caso sólo compiten las
    # direcciones gráficas, que llevan el nombre como pie y no como materia.
    titulo = verbal.nickname or verbal.short
    letrable = supported(titulo.upper(), "athletic") and supported(titulo.title(), "heritage")

    styles = [*STYLES, "symbolic", "heraldic"]
    if symbol == "rose":
        styles.append("floral")
    if symbol == "abstract":
        styles.append("radial")
    # Reparto deliberado de direcciones. El escudo pesaba **dieciséis** frente a
    # 0,15 de las rotuladas, así que 88 de cada 100 marcas eran heráldicas y la
    # familia rotulada —la del béisbol de verdad: wordmark, parche y gorra— no
    # aparecía nunca. La personalidad del club inclina el reparto; no lo decide.
    weights = [
        1.2 + organization.community_reach * 0.5,  # heritage: script y tradición
        1.3 + organization.risk_tolerance * 0.7,  # athletic: bloque y empuje
        1.1 + organization.community_reach * 0.4,  # seal: parche redondo
        0.9 + organization.ambition * 0.5,  # ligature: monograma de gorra
        0.8 + organization.risk_tolerance * 0.3,  # pennant: banderín
        2.3,  # symbolic: la figura sola, el parche, el banderín
        3.6,  # heraldic: el escudo, que sigue siendo lo más común
    ] + [0.9] * (len(styles) - 7)
    if not letrable:
        weights = [
            0.0 if estilo in STYLES else peso for estilo, peso in zip(styles, weights, strict=True)
        ]
    design_style = direction_rng.choices(styles, weights=weights, k=1)[0]

    references = [
        IdentityReference(
            subject="territory",
            value=f"{place_name}, {country_code}" if country_code else place_name,
            status=(
                ReferenceStatus.VERIFIED
                if territory_confidence in {"observed", "verified"}
                else ReferenceStatus.GENERATED
            ),
            source="gazetteer/contexto territorial persistido",
            note="Se usa el topónimo; no se deducen tradiciones o símbolos culturales no documentados.",
        ),
        IdentityReference(
            subject="institutional_character",
            value=(
                f"ambición {organization.ambition:.2f}, riesgo {organization.risk_tolerance:.2f}, "
                f"arraigo {organization.community_reach:.2f}"
            ),
            status=ReferenceStatus.GENERATED,
            source="simulation.generation.organization",
            note="Rasgos ficticios de esta institución, no atributos del territorio real.",
        ),
        IdentityReference(
            subject="cultural_history",
            value="sin referencia curada disponible",
            status=ReferenceStatus.UNAVAILABLE,
            source="",
            note="El generador no inventó un hecho histórico para completar la identidad.",
        ),
    ]
    status = "fictional_generated"
    if real_institution:
        status = "fictional_sports_identity_for_documented_institution"
        references.append(
            IdentityReference(
                subject="institution",
                value=real_institution["name"],
                status=ReferenceStatus.DOCUMENTED_INSTITUTION,
                source=real_institution.get("source", "catálogo institucional"),
                note=(
                    "El nombre institucional está documentado. Los logos y la identidad deportiva "
                    "son ficticios y no se presentan como marca oficial."
                ),
            )
        )

    typography = (
        Typography.SLAB if design_style in ("heritage", "seal", "ligature") else Typography.BLOCK
    )
    visual = VisualLanguage(
        symbol_family=verbal.family,
        preferred_symbols=[symbol] if design_style in GRAPHIC_STYLES else [],
        geometry="primitivas, curvas y símbolos paramétricos en árbol de composición",
        container_policy="opcional; seleccionado por la gramática de cada variante",
        symmetry="simetría funcional con asimetría controlada en giro y ornamentos",
        typography=typography,
        complexity_target="la mínima que preserve jerarquía y reconocimiento",
        color_principle="paleta OKLCH con contraste gráfico ≥3:1 y texto ≥4.5:1",
    )
    naming = NamingProfile(
        official_name=verbal.full,
        short_name=verbal.short,
        initials=verbal.initials,
        nickname=verbal.nickname or None,
        sporting_demonym=verbal.sporting_demonym,
        grammar=verbal.grammar,
        concept_family=verbal.family,
        concept=verbal.concept,
        candidates_considered=verbal.candidates_considered,
        rationale=verbal.rationale,
        motivation=getattr(verbal, "motivation", ""),
        story=getattr(verbal, "story", ""),
        formation=getattr(verbal, "formation", ""),
        root=getattr(verbal, "root", ""),
    )
    # Los colores son del club, no de cada intento de escudo: se componen una
    # sola vez, con su propia subsemilla, y todas las candidatas los reciben.
    # Si cada candidata sorteara su paleta, la identidad del club dependería de
    # cuál de los siete dibujos acabara ganando.
    colores = club_palette(
        random.Random(derive_seed(identity_seed, "palette")),
        ambition=organization.ambition,
        risk_tolerance=organization.risk_tolerance,
        community_reach=organization.community_reach,
    )
    agrupados = colores.grouped()
    club_colors = ClubColors(
        scheme=colores.scheme,
        metal=colores.metal_name,
        primary=[Swatch(**muestra) for muestra in agrupados["primary"]],
        secondary=[Swatch(**muestra) for muestra in agrupados["secondary"]],
        tertiary=[Swatch(**muestra) for muestra in agrupados["tertiary"]],
        rationale=colores.rationale,
    )
    profile = IdentityProfile(
        seed=identity_seed,
        institution_type=institution_type,
        sports_identity_status=status,
        territory={"place": place_name, "country_code": country_code},
        foundation_year=foundation_year,
        foundation_context=_foundation_context(organization, place_name),
        values={
            "ambition": organization.ambition,
            "risk_tolerance": organization.risk_tolerance,
            "community_reach": organization.community_reach,
        },
        references=references,
        naming=naming,
        visual_language=visual,
        palette=club_colors,
        rationale=(
            f"Nombre y sistema visual nacen del concepto creativo «{verbal.concept}» "
            f"({verbal.family}) y de la cultura institucional simulada; dirección {design_style}."
        ),
    )
    candidates: list[tuple[LogoSpec, LogoQuality]] = []
    for index in range(7):
        spec = compose_identity_logo(
            random.Random(derive_seed(identity_seed, "logo", index)),
            place_name=profile.territory["place"],
            nickname=profile.naming.nickname or profile.naming.short_name,
            short_name=profile.naming.short_name,
            concept_family=profile.naming.concept_family,
            ambition=profile.values["ambition"],
            risk_tolerance=profile.values["risk_tolerance"],
            community_reach=profile.values["community_reach"],
            design_style=design_style,
            symbol=symbol,
            founded=foundation_year,
            palette=colores.palette,
        )
        candidates.append((spec, evaluate_logo(spec, verbal.family)))
        if index >= 2 and (logo_registry is None or logo_registry.accepts(spec)):
            break
    eligible = [
        item
        for item in candidates
        if item[1].bounds == 1.0 and (logo_registry is None or logo_registry.accepts(item[0]))
    ]
    if not eligible:
        # Si la estructura se saturó, explorar una dirección distinta, no
        # aceptar silenciosamente el mismo dibujo con otro color.
        for index, alternative in enumerate(styles):
            spec = compose_identity_logo(
                random.Random(derive_seed(identity_seed, "alternative", index)),
                place_name=place_name,
                nickname=verbal.nickname or verbal.short,
                short_name=verbal.short,
                concept_family=verbal.family,
                ambition=organization.ambition,
                risk_tolerance=organization.risk_tolerance,
                community_reach=organization.community_reach,
                design_style=alternative,
                symbol=symbol,
                founded=foundation_year,
                palette=colores.palette,
            )
            quality = evaluate_logo(spec, verbal.family)
            if quality.bounds == 1 and (logo_registry is None or logo_registry.accepts(spec)):
                eligible.append((spec, quality))
    primary, primary_quality = max(eligible or candidates, key=lambda item: item[1].score)
    if logo_registry is not None:
        logo_registry.claim(primary)
    variants = _coordinated_variants(primary, verbal, identity_seed, place_name)
    quality = {
        name: evaluate_logo(spec, verbal.family).as_dict() for name, spec in variants.items()
    }
    actual_symbols = [symbol] if primary.design_style in GRAPHIC_STYLES else []
    profile = profile.model_copy(
        update={
            "visual_language": profile.visual_language.model_copy(
                update={"preferred_symbols": actual_symbols}
            ),
            "rationale": profile.rationale
            + f" Seleccionada {primary.design_style}, calidad heurística {primary_quality.score:.2f}.",
        }
    )
    return IdentitySystem(
        seed=identity_seed,
        profile=profile,
        logos=variants,
        quality=quality,
    )


def redesign_identity_system(
    previous: IdentitySystem,
    *,
    reason: str,
    **generation: Any,
) -> IdentitySystem:
    """Crea una revisión sólo cuando un acontecimiento la solicita.

    El llamador debe proporcionar los mismos argumentos que a
    `build_identity_system`, incluida una semilla nueva derivada del evento.
    Se conserva el artefacto anterior completo: nombre, perfil, composiciones y
    versiones siguen siendo reconstruibles.
    """
    if not reason.strip():
        raise ValueError("un rediseño institucional necesita un motivo")
    current = build_identity_system(**generation)
    archived = previous.as_dict()
    archived["history"] = []
    return current.model_copy(
        update={
            "revision": previous.revision + 1,
            "revision_reason": reason.strip(),
            "history": [*previous.history, archived],
        }
    )
