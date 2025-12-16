#!/usr/bin/env python3

from pathlib import Path
import sys

# Make shared helpers importable.
REPO_ROOT = Path(__file__).resolve().parents[2]
MVUM_DIR = REPO_ROOT / "projects" / "mvum"
sys.path.append(str(REPO_ROOT))
sys.path.append(str(MVUM_DIR))

from functions import (  # type: ignore
    delete_kmls,
    ensure_placemark_names,
    inject_generic_description_table,
    inject_labelstyle,
    make_kmz,
    set_kml_polygon_styles,
    vector_translate_to_kml,
)

# ---------------------------
# CONFIG
# ---------------------------
LABEL_FIELDS: list[str] = ["GMUID"]
LINE_WIDTH = "2"
# Alternating bright fills (AABBGGRR) for GMU polygons.
PALETTE = [
    "ff00ffff",  # cyan
    "ff00ff00",  # green
    "ffffa500",  # orange
    "ffff00ff",  # magenta
    "ff00a5ff",  # yellow-ish
]

PROJECT_DIR = Path(__file__).resolve().parent
INPUT_SHP = PROJECT_DIR / "inputs" / "Game_Management_Units_(GMUs)__CPW.shp"
OUTPUT_DIR = PROJECT_DIR / "outputs"


def export_gmu(trails_shp: Path) -> tuple[Path, Path] | None:
    layer_name = "Game_Management_Units_(GMUs)__CPW"
    out_kml = OUTPUT_DIR / "CO_GMUs.kml"

    sql = f"""
        SELECT
            *,
            GMUID AS NAME,
            GMUID AS NAME_LONG,
            "PEN(c:#ffffffff,w:{LINE_WIDTH}px);BRUSH(fc:#3dffffff)" AS OGR_STYLE
        FROM "{layer_name}"
    """

    vector_translate_to_kml(
        shp_path=str(trails_shp),
        out_kml=str(out_kml),
        sql_statement=sql,
        export_layer_name="co_gmus",
        spat_filter=None,
    )

    ensure_placemark_names(out_kml, LABEL_FIELDS, overwrite=True)
    inject_labelstyle(out_kml, label_color="ff00ffff", label_scale="12.0")
    inject_generic_description_table(
        out_kml,
        priority_fields=[
            "GMUID",
            "COUNTY",
            "DEERDAU",
            "ELKDAU",
            "ANTDAU",
            "MOOSEDAU",
            "BEARDAU",
            "LIONDAU",
            "ACRES",
            "SQ_MILES",
            "INPUT_DATE",
        ],
        heading="Colorado GMUs",
    )
    set_kml_polygon_styles(
        out_kml,
        field_name="GMUID",
        palette=PALETTE,
        line_width=LINE_WIDTH,
        fill_alpha="33",  # ~20% opacity applied to palette colors
    )
    out_kmz = OUTPUT_DIR / "CO_GMUs.kmz"
    make_kmz(out_kml, out_kmz, extra_files=None)
    delete_kmls([out_kml])
    return out_kml, out_kmz


def main() -> int:
    trails_shp = INPUT_SHP
    if not trails_shp.exists():
        print(f"ERROR: GMU shapefile not found: {trails_shp}", file=sys.stderr)
        return 2

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    result = export_gmu(trails_shp)
    if not result:
        print("No GMU export produced.")
        return 3

    print(f"Created GMU KMZ in {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
