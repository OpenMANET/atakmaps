#!/usr/bin/env python3

from pathlib import Path
import sys

from functions import (
    add_point_label_folder_from_lines,
    apply_atak_style_and_region,
    colorize_lines_by_access,
    combine_kml_layers,
    delete_kmls,
    duplicate_simpledata_to_data,
    embed_label_points_in_multigeometry,
    ensure_placemark_names,
    get_layer_name,
    has_features,
    harmonize_document_names,
    inject_description_table,
    inject_labelstyle,
    make_kmz,
    make_zip_archive,
    run_export_with_gdal,
)

# ---------------------------
# CONFIG
# ---------------------------
PROJECT_DIR = Path(__file__).resolve().parent
SHAPEFILES_DIR = PROJECT_DIR / "inputs"
OUTPUT_DIR = PROJECT_DIR / "outputs"

INPUT_SHP_TRAILS = SHAPEFILES_DIR / "MVUM_Symbology_-_Motor_Vehicle_Use_Map_Trails.shp"
INPUT_SHP_ROADS = SHAPEFILES_DIR / "MVUM_Symbology_-_Motor_Vehicle_Use_Map_Roads.shp"
OUTPUT_KML = OUTPUT_DIR / INPUT_SHP_TRAILS.with_suffix(".kml").name
OUTPUT_KMZ = OUTPUT_DIR / INPUT_SHP_TRAILS.with_suffix(".kmz").name
# Force stable KML layer/schema names to match legacy exports.
LAYER_EXPORT_NAME_TRAILS = "mvum_symbology__motor_vehicle_use_map_trails"
LAYER_EXPORT_NAME_ROADS = "mvum_symbology__motor_vehicle_use_map_roads"
# Optional spatial filter (minx, miny, maxx, maxy). Set to None for all data.
SPATIAL_FILTER: tuple[float, float, float, float] | None = None

# Generate per-state KMLs using coarse bounding boxes; all are packaged into the KMZ.
RUN_ALL_STATES = True
STATE_ARCHIVE_ZIP = OUTPUT_DIR / "MVUM_states.zip"
DEFAULT_STATES: list[str] = ["CO"]
# Bounding boxes (xmin, ymin, xmax, ymax) for CONUS + AK/HI.
STATE_BBOXES: dict[str, tuple[float, float, float, float]] = {
    "AL": (-88.473227, 30.223334, -84.88908, 35.008028),
    "AK": (-179.148909, 51.214183, 179.77847, 71.365162),
    "AZ": (-114.81651, 31.332177, -109.045223, 37.00426),
    "AR": (-94.617919, 33.004106, -89.644395, 36.4996),
    "CA": (-124.409591, 32.534156, -114.131211, 42.009518),
    "CO": (-109.060253, 36.992426, -102.041524, 41.003444),
    "CT": (-73.727775, 40.980144, -71.786994, 42.050587),
    "DE": (-75.788658, 38.451013, -75.048939, 39.839007),
    "DC": (-77.119759, 38.791645, -76.909395, 38.99511),
    "FL": (-87.634938, 24.523096, -80.031362, 31.000888),
    "GA": (-85.605165, 30.357851, -80.839729, 35.000659),
    "HI": (-178.334698, 18.910361, -154.806773, 28.402123),
    "ID": (-117.243027, 41.988057, -111.043564, 49.001146),
    "IL": (-91.513079, 36.970298, -87.494756, 42.508481),
    "IN": (-88.09776, 37.771742, -84.784579, 41.760592),
    "IA": (-96.639704, 40.375501, -90.140061, 43.501196),
    "KS": (-102.051744, 36.993016, -94.588413, 40.003162),
    "KY": (-89.571509, 36.497129, -81.964971, 39.147458),
    "LA": (-94.043147, 28.928609, -88.817017, 33.019457),
    "ME": (-71.083924, 42.977764, -66.949895, 47.459686),
    "MD": (-79.487651, 37.911717, -75.048939, 39.723043),
    "MA": (-73.508142, 41.237964, -69.928393, 42.886589),
    "MI": (-90.418136, 41.696118, -82.413474, 48.2388),
    "MN": (-97.239209, 43.499356, -89.491739, 49.384358),
    "MS": (-91.655009, 30.173943, -88.097888, 34.996052),
    "MO": (-95.774704, 35.995683, -89.098843, 40.61364),
    "MT": (-116.050003, 44.358221, -104.039138, 49.00139),
    "NE": (-104.053514, 39.999998, -95.30829, 43.001708),
    "NV": (-120.005746, 35.001857, -114.039648, 42.002207),
    "NH": (-72.557247, 42.69699, -70.610621, 45.305476),
    "NJ": (-75.559614, 38.928519, -73.893979, 41.357423),
    "NM": (-109.050173, 31.332301, -103.001964, 37.000232),
    "NY": (-79.762152, 40.496103, -71.856214, 45.01585),
    "NC": (-84.321869, 33.842316, -75.460621, 36.588117),
    "ND": (-104.0489, 45.935054, -96.554507, 49.000574),
    "OH": (-84.820159, 38.403202, -80.518693, 41.977523),
    "OK": (-103.002565, 33.615833, -94.430662, 37.002206),
    "OR": (-124.566244, 41.991794, -116.463504, 46.292035),
    "PA": (-80.519891, 39.7198, -74.689516, 42.26986),
    "RI": (-71.862772, 41.146339, -71.12057, 42.018798),
    "SC": (-83.35391, 32.0346, -78.54203, 35.215402),
    "SD": (-104.057698, 42.479635, -96.436589, 45.94545),
    "TN": (-90.310298, 34.982972, -81.6469, 36.678118),
    "TX": (-106.645646, 25.837377, -93.508292, 36.500704),
    "VI": (-65.085452, 17.673976, -64.564907, 18.412655),
    "UT": (-114.052962, 36.997968, -109.041058, 42.001567),
    "VT": (-73.43774, 42.726853, -71.464555, 45.016659),
    "VA": (-83.675395, 36.540738, -75.242266, 39.466012),
    "WA": (-124.763068, 45.543541, -116.915989, 49.002494),
    "WV": (-82.644739, 37.201483, -77.719519, 40.638801),
    "WI": (-92.888114, 42.491983, -86.805415, 47.080621),
    "WY": (-111.056888, 40.994746, -104.05216, 45.005904),
}

# Fields to try (in order) for ATAK labels; first non-empty wins.
# LONGNAME is populated from the shapefile's NAME field so we retain
# the original NAME attribute in ExtendedData instead of losing it to <name>.
LABEL_FIELDS: list[str] = ["ID", "LONGNAME"]
LABEL_POINT_FOLDER_NAME = "Trail Labels (points)"
# If True, add a Point into each Placemark's geometry (as MultiGeometry) so
# ATAK can render labels anchored to the point while retaining the line.
EMBED_LABEL_POINTS = True
ACCESS_FIELDS_TRAILS = [
    "PASSENGERV",
    "HIGHCLEARA",
    "ATV",
    "TRUCK",
    "MOTORCYCLE",
    # Include tracked/snowmobile style access flags if present.
    "SNOWMOBILE",
    "TRACKED_OH",
    "TRACKED__2",
]
ACCESS_COLOR_ALLOWED = "ff00ff00"  # green (AA BB GG RR)
ACCESS_COLOR_DENIED = "ff0000ff"   # red

# Roads-specific styling
ACCESS_FIELDS_ROADS = ACCESS_FIELDS_TRAILS
ROADS_COLOR_ALLOWED = "ff00a5ff"  # orange (AABBGGRR)
ROADS_COLOR_DENIED = "ff0000ff"   # red

# LineStyle (KML AABBGGRR)
LINE_COLOR = "ff0000ff"   # red (base; overridden inline per feature)
LINE_WIDTH = "2"          # px

# LabelStyle (KML AABBGGRR)
LABEL_COLOR = "ff00ffff"  # yellow
LABEL_SCALE = "1.5"

# ATAK map-specific customizations. Adjust these values to change how the
# generated KML/KMZ looks when loaded in ATAK.
ENABLE_ATAK_STYLE = True
ATAK_STYLE_ID_TRAILS = "AtakStyleTrails"
ATAK_STYLE_ID_ROADS = "AtakStyleRoads"
# Set to a filename or URL if you want an icon; None means omit IconStyle.
ATAK_ICON_HREF: str | None = None
ATAK_ICON_SCALE = "2.0"
ATAK_POLY_COLOR = "ff000000"
ATAK_POLY_OUTLINE = "0"
ATAK_REGION = None


def main() -> int:
    trails_shp = Path(INPUT_SHP_TRAILS)
    roads_shp = Path(INPUT_SHP_ROADS)
    if not trails_shp.exists():
        print(f"ERROR: Trails shapefile not found: {trails_shp}", file=sys.stderr)
        return 2
    if not roads_shp.exists():
        print(f"ERROR: Roads shapefile not found: {roads_shp}", file=sys.stderr)
        return 2

    trail_layer_name = get_layer_name(str(trails_shp))
    road_layer_name = get_layer_name(str(roads_shp))

    extras = []
    if ENABLE_ATAK_STYLE and ATAK_ICON_HREF:
        icon_path = Path(ATAK_ICON_HREF)
        if icon_path.exists():
            extras.append(ATAK_ICON_HREF)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SHAPEFILES_DIR.mkdir(parents=True, exist_ok=True)

    state_order = list(STATE_BBOXES) if RUN_ALL_STATES else DEFAULT_STATES
    state_bboxes = {abbr: STATE_BBOXES[abbr] for abbr in state_order if abbr in STATE_BBOXES}
    if not state_bboxes:
        print("ERROR: no state bounding boxes available.", file=sys.stderr)
        return 3

    print("Generating per-state KMLs/KMZs (roads + trails)...")
    produced_kmzs: list[str] = []
    for state, bbox in state_bboxes.items():
        has_trails = has_features(trails_shp, bbox)
        has_roads = has_features(roads_shp, bbox)
        if not has_trails and not has_roads:
            print(f"Skipping {state}: no trails or roads in bbox.")
            continue

        out_trails: Path | None = None
        out_roads: Path | None = None
        n_trail_names = 0
        n_road_names = 0

        if has_trails:
            out_trails = OUTPUT_DIR / f"MVUM_{state}_trails.kml"
            run_export_with_gdal(
                str(trails_shp),
                str(out_trails),
                trail_layer_name,
                bbox,
                LAYER_EXPORT_NAME_TRAILS,
                LINE_COLOR,
                LINE_WIDTH,
            )
            n_trail_names = ensure_placemark_names(out_trails, LABEL_FIELDS, overwrite=True)
            inject_labelstyle(out_trails, LABEL_COLOR, LABEL_SCALE)
            harmonize_document_names(out_trails, LAYER_EXPORT_NAME_TRAILS)
            if ENABLE_ATAK_STYLE:
                apply_atak_style_and_region(
                    out_trails,
                    style_id=ATAK_STYLE_ID_TRAILS,
                    icon_href=ATAK_ICON_HREF,
                    icon_scale=ATAK_ICON_SCALE,
                    poly_color=ATAK_POLY_COLOR,
                    poly_outline=ATAK_POLY_OUTLINE,
                    label_color=LABEL_COLOR,
                    label_scale=LABEL_SCALE,
                    line_color=LINE_COLOR,
                    line_width=LINE_WIDTH,
                    region=None,
                )
            if EMBED_LABEL_POINTS:
                embed_label_points_in_multigeometry(str(trails_shp), out_trails, label_fields=LABEL_FIELDS)
            else:
                add_point_label_folder_from_lines(
                    str(trails_shp),
                    out_trails,
                    folder_name=LABEL_POINT_FOLDER_NAME,
                    style_id=ATAK_STYLE_ID_TRAILS if ENABLE_ATAK_STYLE else "",
                    label_fields=LABEL_FIELDS,
                    schema_id=LAYER_EXPORT_NAME_TRAILS,
                )
            duplicate_simpledata_to_data(out_trails)
            inject_description_table(out_trails)
            colorize_lines_by_access(
                out_trails,
                allow_fields=ACCESS_FIELDS_TRAILS,
                color_allowed=ACCESS_COLOR_ALLOWED,
                color_denied=ACCESS_COLOR_DENIED,
                width=LINE_WIDTH,
            )

        if has_roads:
            out_roads = OUTPUT_DIR / f"MVUM_{state}_roads.kml"
            run_export_with_gdal(
                str(roads_shp),
                str(out_roads),
                road_layer_name,
                bbox,
                LAYER_EXPORT_NAME_ROADS,
                LINE_COLOR,
                LINE_WIDTH,
            )
            n_road_names = ensure_placemark_names(out_roads, LABEL_FIELDS, overwrite=True)
            inject_labelstyle(out_roads, LABEL_COLOR, LABEL_SCALE)
            harmonize_document_names(out_roads, LAYER_EXPORT_NAME_ROADS)
            if ENABLE_ATAK_STYLE:
                apply_atak_style_and_region(
                    out_roads,
                    style_id=ATAK_STYLE_ID_ROADS,
                    icon_href=ATAK_ICON_HREF,
                    icon_scale=ATAK_ICON_SCALE,
                    poly_color=ATAK_POLY_COLOR,
                    poly_outline=ATAK_POLY_OUTLINE,
                    label_color=LABEL_COLOR,
                    label_scale=LABEL_SCALE,
                    line_color=LINE_COLOR,
                    line_width=LINE_WIDTH,
                    region=None,
                )
            if EMBED_LABEL_POINTS:
                embed_label_points_in_multigeometry(str(roads_shp), out_roads, label_fields=LABEL_FIELDS)
            else:
                add_point_label_folder_from_lines(
                    str(roads_shp),
                    out_roads,
                    folder_name=LABEL_POINT_FOLDER_NAME,
                    style_id=ATAK_STYLE_ID_ROADS if ENABLE_ATAK_STYLE else "",
                    label_fields=LABEL_FIELDS,
                    schema_id=LAYER_EXPORT_NAME_ROADS,
                )
            duplicate_simpledata_to_data(out_roads)
            inject_description_table(out_roads)
            colorize_lines_by_access(
                out_roads,
                allow_fields=ACCESS_FIELDS_ROADS,
                color_allowed=ROADS_COLOR_ALLOWED,
                color_denied=ROADS_COLOR_DENIED,
                width=LINE_WIDTH,
            )

        kmls = [p for p in (out_trails, out_roads) if p]
        if not kmls:
            print(f"Skipping {state}: no KML produced after processing.")
            continue

        if len(kmls) == 2:
            combined = OUTPUT_DIR / f"MVUM_{state}.kml"
            combine_kml_layers(kmls[0], kmls[1], combined, doc_name=f"MVUM Roads and Trails - {state}")
        else:
            combined = kmls[0]

        # Per-state KMZ for ATAK import (combined)
        state_kmz = OUTPUT_DIR / f"MVUM_{state}.kmz"
        make_kmz(combined, state_kmz, extra_files=extras)
        produced_kmzs.append(state_kmz)
        print(f"State {state}: trails named {n_trail_names}, roads named {n_road_names}, files {combined}, {state_kmz}")

        delete_kmls([out_trails, out_roads, combined])

    make_zip_archive(produced_kmzs, STATE_ARCHIVE_ZIP)
    zip_size_mb = Path(STATE_ARCHIVE_ZIP).stat().st_size / (1024 * 1024)
    print(f"Created archive: {STATE_ARCHIVE_ZIP} ({zip_size_mb:.1f} MB) containing {len(produced_kmzs)} state KMZs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
