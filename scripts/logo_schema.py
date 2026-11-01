"""Publica el contrato del logo a partir del modelo de Pydantic.

El modelo es la **fuente**: de él sale el JSON Schema que documenta qué es un
logo —qué capas existen, qué rangos admite cada una, qué motivos hay— y, si
algún día la interfaz vuelve a interpretar la especificación en el cliente, los
tipos de TypeScript. Un contrato escrito a mano en dos idiomas se separa solo
(ADR 0012, R5).

El esquema publicado está versionado en el repositorio y una prueba falla si se
queda obsoleto: un artefacto generado sin guardia miente a la primera.

    python scripts/logo_schema.py --out docs/logo-schema.json
    python scripts/logo_schema.py --typescript frontend/src/lib/api/logo.d.ts
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from simulation.identity.motifs import MOTIFS
from simulation.identity.spec import (
    LOGO_SCHEMA_VERSION,
    Anchor,
    ColorRole,
    LogoSpec,
    Shape,
    TextLayout,
    Typography,
)

CABECERA = """// Generado por scripts/logo_schema.py — no editar a mano.
// La fuente del contrato es simulation/identity/spec.py; `make logo-schema`
// regenera este fichero. Un contrato escrito dos veces se separa solo.

"""


def union(nombre: str, valores: list[str]) -> str:
    opciones = " | ".join(f"'{valor}'" for valor in sorted(valores))
    return f"export type {nombre} = {opciones};\n\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", type=Path, default=Path("docs/logo-schema.json"), help="JSON Schema"
    )
    parser.add_argument(
        "--typescript", type=Path, default=None, help="además, los tipos de TypeScript"
    )
    parser.add_argument(
        "--check", action="store_true", help="no escribe: falla si el esquema está obsoleto"
    )
    args = parser.parse_args()

    esquema = json.dumps(LogoSpec.model_json_schema(), indent=2, ensure_ascii=False) + "\n"
    if args.check:
        actual = args.out.read_text(encoding="utf-8") if args.out.exists() else ""
        if actual != esquema:
            print(f"{args.out} está obsoleto: ejecuta `make logo-schema`", file=sys.stderr)
            return 1
        print(f"{args.out} al día")
        return 0
    args.out.write_text(esquema, encoding="utf-8")
    print(f"JSON Schema en {args.out}")

    if args.typescript is None:
        return 0

    piezas = [CABECERA]
    piezas.append(f"export const LOGO_SCHEMA_VERSION = {LOGO_SCHEMA_VERSION};\n\n")
    piezas.append(union("LogoShape", [s.value for s in Shape]))
    piezas.append(union("LogoAnchor", [a.value for a in Anchor]))
    piezas.append(union("LogoColorRole", [r.value for r in ColorRole]))
    piezas.append(union("LogoTextLayout", [t.value for t in TextLayout]))
    piezas.append(union("LogoTypography", [t.value for t in Typography]))
    piezas.append(union("LogoMotif", sorted(MOTIFS)))
    piezas.append(
        """export interface LogoPlacement {
  anchor: LogoAnchor;
  dx: number;
  dy: number;
  scale: number;
  rotate: number;
}

export interface LogoLayerBase {
  z: number;
  placement: LogoPlacement;
  fill: string;
  stroke: string;
  stroke_width: number;
  opacity: number;
  min_size: number;
}

export interface LogoShapeLayer extends LogoLayerBase {
  kind: 'shape';
  shape: LogoShape;
}

export interface LogoMotifLayer extends LogoLayerBase {
  kind: 'motif';
  motif: LogoMotif;
  params: Record<string, number>;
  repeat: number;
  spread: number;
}

export interface LogoTextLayer extends LogoLayerBase {
  kind: 'text';
  text: string;
  layout: LogoTextLayout;
  typography: LogoTypography;
  size: number;
  letter_spacing: number;
}

export type LogoLayer = LogoShapeLayer | LogoMotifLayer | LogoTextLayer;

export interface LogoPalette {
  field: string;
  mark: string;
  ink: string;
  accent: string;
  paper: string;
}

export interface LogoSpec {
  schema_version: number;
  palette: LogoPalette;
  layers: LogoLayer[];
  rationale: string;
}
"""
    )
    args.typescript.write_text("".join(piezas), encoding="utf-8")
    print(f"tipos de TypeScript en {args.typescript}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
