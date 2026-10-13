"""Genera le istanze statiche dei font variabili usati dai sottotitoli ASS.

libass (ffmpeg-full) carica i font variabili di assets/fonts/ solo nell'istanza di default (Inter = Regular) e non sa
scegliere il peso: per avere Inter SemiBold/Bold/ExtraBold servono file statici. Anton è già statico e viene solo
copiato. I brand esterni tengono le proprie istanze statiche in <brands_dir>/<slug>/fonts (o ass/fonts): stessa
ricetta, cambiando INSTANCES, SRC e OUT.

Uso (serve fontTools, NON presente nel venv del toolkit — basta un Python che lo abbia):
    /usr/bin/python3 "$(yt-config --get plugin_root)/scripts/yt/assets/ass/make_static_fonts.py"

Output: assets/ass/fonts/*.ttf + licenze OFL (nessun Reserved Font Name nei font sorgente,
quindi le istanze statiche possono mantenere il nome di famiglia, come i "static" di Google Fonts).
"""
from __future__ import annotations

import shutil
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "fonts"
OUT = HERE / "fonts"

# (file sorgente, coordinate assi, famiglia, stile) → file "<Famiglia>-<Stile>.ttf"
INSTANCES = [
    ("Inter[opsz,wght].ttf", {"wght": 600, "opsz": 32}, "Inter", "SemiBold"),
    ("Inter[opsz,wght].ttf", {"wght": 700, "opsz": 32}, "Inter", "Bold"),
    ("Inter[opsz,wght].ttf", {"wght": 800, "opsz": 32}, "Inter", "ExtraBold"),
]
WEIGHTS = {"SemiBold": 600, "Bold": 700, "ExtraBold": 800}


def set_names(font: TTFont, family: str, style: str) -> None:
    """Nomi stile Google Fonts static: i pesi non-RIBBI diventano famiglia '<Fam> <Stile>'."""
    ribbi = style == "Bold"
    legacy_family = family if ribbi else f"{family} {style}"
    legacy_sub = "Bold" if ribbi else "Regular"
    ps = f"{family.replace(' ', '')}-{style}"
    table = font["name"]
    for name_id in (1, 2, 3, 4, 6, 16, 17, 25):
        table.removeNames(nameID=name_id)
    table.setName(legacy_family, 1, 3, 1, 0x409)
    table.setName(legacy_sub, 2, 3, 1, 0x409)
    table.setName(f"{ps};static", 3, 3, 1, 0x409)
    table.setName(f"{family} {style}", 4, 3, 1, 0x409)
    table.setName(ps, 6, 3, 1, 0x409)
    if not ribbi:
        table.setName(family, 16, 3, 1, 0x409)
        table.setName(style, 17, 3, 1, 0x409)
    os2 = font["OS/2"]
    os2.usWeightClass = WEIGHTS[style]
    os2.fsSelection = (os2.fsSelection & ~0b1100001) | (0b100000 if ribbi else 0b1000000)
    font["head"].macStyle = 1 if ribbi else 0


COPY = ["Anton-Regular.ttf", "OFL-Anton.txt", "OFL-Inter.txt"]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for src, coords, family, style in INSTANCES:
        font = TTFont(SRC / src)
        static = instancer.instantiateVariableFont(font, coords)
        set_names(static, family, style)
        out = f"{family.replace(' ', '')}-{style}.ttf"
        static.save(OUT / out)
        print(f"{out}: {coords}")
    for name in COPY:
        shutil.copy2(SRC / name, OUT / name)
        print(f"{name}: copiato")


if __name__ == "__main__":
    main()
