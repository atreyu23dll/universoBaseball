"""Ilustraciones vectoriales por curvas y geometría; estilo versionado explícito."""

import math


def path(d, color="mark", stroke="ink", width=0.018):
    return {"kind": "path", "d": d, "color": color, "outline": stroke, "width": width}


def illustrated(motif, params):
    if motif == "oak":
        return [
            path(
                "M .43 .89 L .46 .6 Q .2 .75 .12 .52 Q .02 .35 .23 .28 Q .21 .06 .44 .16 Q .57 -.01 .69 .2 Q .91 .13 .9 .39 Q 1 .62 .74 .65 L .55 .6 L .59 .89 Z"
            ),
            path(
                "M .49 .78 L .5 .35 M .5 .58 L .29 .4 M .51 .52 L .72 .34 M .49 .7 L .71 .55",
                "none",
                "field",
                0.027,
            ),
        ]
    if motif == "bridge":
        pieces = [
            path(
                "M .06 .33 L .94 .33 L .94 .86 L .83 .86 L .83 .6 Q .73 .39 .63 .6 L .63 .86 L .56 .86 L .56 .58 Q .5 .42 .44 .58 L .44 .86 L .37 .86 L .37 .6 Q .27 .39 .17 .6 L .17 .86 L .06 .86 Z"
            ),
            path("M .03 .26 L .97 .26 L .97 .34 L .03 .34 Z", "accent"),
        ]
        for i in range(9):
            x = 0.1 + i * 0.1
            pieces.append(path(f"M {x} .27 L {x} .33", "none", "field", 0.012))
        return pieces
    if motif in {"bull", "jaguar"}:
        pieces = [
            path(
                "M .29 .28 L .1 .13 Q .04 .4 .3 .47 L .33 .72 L .5 .91 L .67 .72 L .7 .47 Q .96 .4 .9 .13 L .71 .28 Q .5 .12 .29 .28 Z"
            ),
            path("M .3 .44 L .44 .51 L .36 .54 Z M .7 .44 L .56 .51 L .64 .54 Z", "paper"),
            path("M .39 .65 Q .5 .59 .61 .65 L .59 .77 L .5 .82 L .41 .77 Z", "field"),
            path("M .44 .69 L .47 .71 M .56 .69 L .53 .71", "none", "paper", 0.025),
            path("M .48 .27 L .4 .4 L .48 .59 L .52 .59 L .6 .4 L .52 .27 Z", "accent", "none"),
        ]
        if motif == "jaguar":
            for x in (0.28, 0.72):
                for y in (0.37, 0.58, 0.65):
                    pieces.append(
                        path(f"M {x} {y} l .025 -.02 l .018 .03 l -.025 .02 Z", "ink", "none")
                    )
        return pieces
    if motif == "cactus":
        return [
            path(
                "M .42 .9 L .42 .6 L .25 .6 Q .14 .6 .14 .49 L .14 .31 Q .2 .22 .26 .31 L .26 .46 L .42 .46 L .42 .16 Q .5 .04 .58 .16 L .58 .57 L .75 .57 L .75 .4 Q .81 .31 .87 .4 L .87 .6 Q .87 .72 .75 .72 L .58 .72 L .58 .9 Z"
            ),
            path(
                "M .48 .2 L .48 .84 M .53 .19 L .53 .84 M .2 .34 L .2 .52 L .36 .52 M .81 .43 L .81 .64 L .64 .64",
                "none",
                "field",
                0.018,
            ),
            path("M .22 .92 Q .5 .83 .8 .92 Z", "accent"),
        ]
    if motif == "comet":
        return [
            path("M .06 .89 Q .22 .49 .59 .15 L .47 .55 Z"),
            path("M .18 .94 Q .56 .85 .85 .47 L .52 .57 Z", "accent"),
            path("M .72 .08 A .23 .23 0 1 1 .719 .08 Z", "paper"),
            path(
                "M .72 .17 L .75 .27 L .85 .3 L .75 .33 L .72 .43 L .69 .33 L .59 .3 L .69 .27 Z",
                "field",
                "none",
            ),
        ]
    if motif == "rose":
        petals = int(max(4, min(9, params.get("petals", 6))))
        pieces = []
        for ring, radius in enumerate((0.31, 0.21, 0.12)):
            for i in range(petals):
                angle = i * math.tau / petals + ring * 0.4
                x, y = 0.5 + radius * math.cos(angle), 0.5 + radius * math.sin(angle)
                r = radius * 0.9
                px, py = -math.sin(angle) * r, math.cos(angle) * r
                pieces.append(
                    path(
                        f"M .5 .5 C {x + px:.4f} {y + py:.4f} {x + px:.4f} {y + py:.4f} {x:.4f} {y:.4f} "
                        f"C {x - px:.4f} {y - py:.4f} {x - px:.4f} {y - py:.4f} .5 .5 Z",
                        "accent" if ring == 1 else "mark",
                    )
                )
        return pieces
    if motif == "bird":
        feathers = int(max(4, min(8, params.get("feathers", 6))))
        pieces = []
        for side in (-1, 1):
            for i in range(feathers):
                x = 0.5 + side * (0.44 - i * 0.045)
                y = 0.14 + i * 0.072
                pieces.append(
                    path(f"M .5 .39 Q {x:.3f} .39 {x:.3f} {y:.3f} L {0.5 + side * 0.12:.3f} .65 Z")
                )
        pieces += [
            path(
                "M .4 .36 Q .38 .18 .53 .19 L .65 .29 L .55 .33 L .56 .7 L .65 .88 L .5 .79 L .35 .88 L .44 .66 Z"
            ),
            path("M .52 .25 L .57 .27 L .53 .29 Z", "ink", "none"),
        ]
        return pieces
    if motif == "elephant":
        span = max(0.16, min(0.26, params.get("ear_span", 0.23)))
        pieces = []
        for side in (-1, 1):
            x = 0.5 + side * span
            edge = 0.5 + side * 0.44
            pieces.append(path(f"M .5 .3 Q {edge} -.02 {edge} .38 Q {edge} .83 {x} .76 L .5 .5 Z"))
        pieces += [
            path(
                "M .32 .26 Q .5 .08 .68 .26 L .63 .57 Q .57 .61 .58 .81 Q .6 .94 .43 .92 L .4 .84 Q .5 .88 .48 .76 L .44 .56 L .35 .51 Z"
            ),
            path("M .35 .5 Q .22 .72 .4 .73 L .42 .62 Z", "paper"),
            path("M .65 .5 Q .78 .72 .6 .73 L .58 .62 Z", "paper"),
            path("M .36 .39 L .44 .42 L .38 .44 Z M .64 .39 L .56 .42 L .62 .44 Z", "ink", "none"),
            path(
                "M .44 .29 Q .5 .25 .56 .29 M .47 .65 L .54 .65 M .48 .72 L .55 .72",
                "none",
                "ink",
                0.012,
            ),
        ]
        return pieces
    if motif == "summit":
        return [
            path("M .04 .84 L .35 .24 L .48 .46 L .67 .12 L .96 .84 Z"),
            path("M .35 .24 L .22 .5 L .34 .44 L .4 .51 L .48 .46 Z", "paper"),
            path("M .67 .12 L .5 .48 L .65 .37 L .72 .46 L .8 .43 Z", "paper"),
            path("M .67 .37 L .59 .8 L .89 .8 Z M .35 .44 L .28 .8 L .44 .8 Z", "field", "none"),
        ]
    if motif in {"wave", "river"}:
        return [
            path(
                "M .05 .79 Q .18 .61 .27 .39 Q .43 .03 .71 .2 Q .9 .29 .79 .48 Q .76 .27 .57 .36 Q .45 .46 .64 .6 Q .78 .71 .95 .6 L .91 .8 Q .5 1 .05 .79 Z"
            ),
            path("M .14 .8 Q .48 .88 .88 .72 M .2 .72 Q .43 .76 .53 .68", "none", "field", 0.028),
        ]
    if motif == "flame":
        return [
            path(
                "M .5 .04 Q .58 .37 .77 .22 Q .71 .47 .86 .56 Q .93 .89 .53 .94 Q .12 .94 .14 .64 Q .16 .48 .29 .36 Q .24 .61 .4 .55 Q .51 .4 .5 .04 Z"
            ),
            path(
                "M .51 .46 Q .5 .64 .64 .62 Q .78 .88 .51 .89 Q .29 .85 .38 .7 Z", "field", "none"
            ),
        ]
    if motif == "ball":
        return [
            path("M .5 .06 A .44 .44 0 1 1 .499 .06 Z", "paper"),
            path("M .23 .14 Q .52 .5 .23 .86 M .77 .14 Q .48 .5 .77 .86", "none", "field", 0.026),
            *[
                path(
                    f"M {0.23 + 0.11 * math.sin(i * math.pi / 7) - 0.035:.3f} {0.18 + i * 0.09:.3f} l .07 -.025 M {0.77 - 0.11 * math.sin(i * math.pi / 7) - 0.035:.3f} {0.18 + i * 0.09:.3f} l .07 .025",
                    "none",
                    "field",
                    0.016,
                )
                for i in range(8)
            ],
        ]
    return None
