#!/usr/bin/env python3

from pathlib import Path
import sys

# Ensure shared helpers are importable.
REPO_ROOT = Path(__file__).resolve().parents[2]
MVUM_DIR = REPO_ROOT / "projects" / "mvum"
sys.path.append(str(REPO_ROOT))
sys.path.append(str(MVUM_DIR))

from functions import (
    delete_kmls,
    ensure_placemark_names,
    embed_label_points_in_multigeometry,
    inject_generic_description_table,
    harmonize_document_names,
    inject_labelstyle,
    make_kmz,
    set_kml_linestyle,
    vector_translate_to_kml,
)
from state_bboxes import DEFAULT_STATES, STATE_BBOXES

# ---------------------------
# CONFIG
# ---------------------------
RUN_ALL_STATES = False
LABEL_FIELDS: list[str] = ["TRAIL_NO", "TRAIL_NAME"]
LINE_COLOR = "ff00ffff"  # bright cyan (AABBGGRR) to distinguish non-motorized
LINE_WIDTH = "2"

PROJECT_DIR = Path(__file__).resolve().parent
INPUT_SHP = PROJECT_DIR / "inputs" / "National_Forest_System_Trails_(Feature_Layer).shp"
OUTPUT_DIR = PROJECT_DIR / "outputs"
STATE_ARCHIVE_ZIP = OUTPUT_DIR / "USFS_trails_states.zip"


def export_state(trails_shp: Path, state: str, bbox: tuple[float, float, float, float]) -> Path | None:
    layer_name = "National_Forest_System_Trails_(Feature_Layer)"
    out_kml = OUTPUT_DIR / f"USFS_trails_{state}.kml"

    sql = f"""
        SELECT
            *,
            COALESCE(TRAIL_NO, TRAIL_NAME) AS NAME,
            COALESCE(TRAIL_NAME, TRAIL_NO) AS NAME_LONG,
            "PEN(c:#{LINE_COLOR},w:{LINE_WIDTH}px)" AS OGR_STYLE
        FROM "{layer_name}"
        WHERE COALESCE(UPPER(TERRA_MOTO),'') <> 'Y'
          AND (MVUM_SYMBO IS NULL OR MVUM_SYMBO = 0)
    """

    vector_translate_to_kml(
        shp_path=str(trails_shp),
        out_kml=str(out_kml),
        sql_statement=sql,
        export_layer_name=f"usfs_trails_{state.lower()}",
        spat_filter=bbox,
    )

    n_named = ensure_placemark_names(out_kml, LABEL_FIELDS, overwrite=True)
    inject_labelstyle(out_kml, label_color="ff00ffff", label_scale="1.5")
    inject_generic_description_table(
        out_kml,
        priority_fields=[
            "NAME_LONG",
            "NAME",
            "TRAIL_NAME",
            "TRAIL_NO",
            "TRAIL_TYPE",
            "TRAIL_CLASS",
            "TRAIL_SURF",
            "SURFACE_FI",
            "TYPICAL_TR",        # grade
            "TYPICAL__1",        # tread width
            "TYPICAL__2",        # cross slope
            "ALLOWED_TE",
            "ALLOWED_SN",
        ],
        heading=f"USFS Trails (non-motorized) - {state}",
    )
    embed_label_points_in_multigeometry(str(trails_shp), out_kml, label_fields=LABEL_FIELDS)
    set_kml_linestyle(out_kml, line_color=LINE_COLOR, line_width=LINE_WIDTH)
    harmonize_document_names(out_kml, f"USFS Trails (non-motorized) - {state}")
    print(f"State {state}: named {n_named} features")
    return out_kml


def main() -> int:
    trails_shp = INPUT_SHP
    if not trails_shp.exists():
        print(f"ERROR: Trails shapefile not found: {trails_shp}", file=sys.stderr)
        return 2

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    state_order = list(STATE_BBOXES) if RUN_ALL_STATES else DEFAULT_STATES
    produced = []

    for state in state_order:
        bbox = STATE_BBOXES.get(state)
        if not bbox:
            continue
        out_kml = export_state(trails_shp, state, bbox)
        if out_kml and out_kml.exists():
            out_kmz = OUTPUT_DIR / f"USFS_trails_{state}.kmz"
            make_kmz(out_kml, out_kmz, extra_files=None)
            produced.append(out_kmz)
            delete_kmls([out_kml])

    if not produced:
        print("No state exports produced.")
        return 3

    print(f"Created {len(produced)} KMZ files in {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
