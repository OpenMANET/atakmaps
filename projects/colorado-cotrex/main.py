#!/usr/bin/env python3

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

from osgeo import gdal, ogr, osr

KML_NS = "http://www.opengis.net/kml/2.2"
NS = {"kml": KML_NS}

# Reuse shared helpers from the MVUM functions module.
REPO_ROOT = Path(__file__).resolve().parents[2]
MVUM_DIR = REPO_ROOT / "projects" / "mvum"
sys.path.append(str(MVUM_DIR))
from functions import (  # type: ignore
    _CDATA,
    _find_simpledata_value,
    _is_allowed_value,
    colorize_lines_by_access,
    duplicate_simpledata_to_data,
    ensure_placemark_names,
    get_layer_name,
    make_kmz,
)

gdal.UseExceptions()

INPUT_SHP = Path(__file__).resolve().parent / "inputs" / "COTREX_Trails.shp"
INPUT_SHP_TRAILHEADS = Path(__file__).resolve().parent / "inputs" / "COTREX_Trailheads.shp"
OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"
OUTPUT_KML = OUTPUT_DIR / "COTREX_Trails.kml"
OUTPUT_KMZ = OUTPUT_DIR / "COTREX_Trails.kmz"
OUTPUT_KML_TRAILHEADS = OUTPUT_DIR / "COTREX_Trailheads.kml"
OUTPUT_KMZ_TRAILHEADS = OUTPUT_DIR / "COTREX_Trailheads.kmz"
LAYER_EXPORT_NAME = "cotrex_trails"
LAYER_EXPORT_NAME_THS = "cotrex_trailheads"

# Line styling: we recolor per-feature based on allowed uses later.
LINE_COLOR = "ffcc66ff"  # pink base (AABBGGRR)
LINE_WIDTH = "2"
ICON_COLOR = "ffcc66ff"  # icon tint (pink)
ICON_SCALE = "1.5"
LABEL_COLOR = "ffffffff"
LABEL_SCALE = "1.2"

# Allowance fields for colorizing and legend.
ALLOW_FIELDS = [
    "hiking",
    "horse",
    "bike",
    "motorcycle",
    "atv",
    "ohv_gt_50",
    "highway_ve",
]
# Use-specific folders and colors (AABBGGRR).
CATEGORIES = [
    ("Hiking", "hiking", "ffcc66ff", "hiking"),              # pink
    ("Horse", "horse", "ffcc99ff", "horse"),                # light pink
    ("Bike", "bike", "ffcc33ff", "bike"),                   # magenta-pink
    ("Motorcycle", "motorcycle", "ffb366ff", "motorcycle"), # warm pink
    ("ATV", "atv", "ffa04dff", "atv"),                      # coral pink
    ("OHV > 50\"", "ohv_gt_50", "ffcc00ff", "ohv_gt_50"),   # vivid magenta
    ("Highway vehicles", "highway_ve", "ff9900ff", "highway_vehicles"),  # bright pink-red
    ("Dogs", "dogs", "ffdbb0ff", "dogs"),                   # pastel pink
]


def export_to_kml() -> None:
    layer_name = get_layer_name(str(INPUT_SHP))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Copy all fields, but set NAME to feature_id for labels and preserve the
    # original name as NAME_LONG. Reproject to WGS84 for KML. Filter out USFS-managed
    # features (handled by dedicated MVUM/USFS layers elsewhere).
    sql = f"""
        SELECT
            *,
            feature_id AS "NAME",
            name AS "NAME_LONG",
            "PEN(c:#{LINE_COLOR},w:{LINE_WIDTH}px)" AS OGR_STYLE
        FROM "{layer_name}"
        WHERE
            manager NOT LIKE '%USFS%' AND
            manager NOT LIKE '%Forest Service%' AND
            manager NOT LIKE '%National Forest%'
    """
    gdal.VectorTranslate(
        destNameOrDestDS=str(OUTPUT_KML),
        srcDS=str(INPUT_SHP),
        format="KML",
        SQLDialect="SQLITE",
        SQLStatement=" ".join(sql.split()),
        layerName=LAYER_EXPORT_NAME,
        dstSRS="EPSG:4326",
    )


def export_trailheads_to_kml() -> None:
    layer_name = get_layer_name(str(INPUT_SHP_TRAILHEADS))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    sql = f"""
        SELECT
            *,
            COALESCE(name, alt_name, CAST(feature_id AS TEXT)) AS "NAME",
            name AS "NAME_LONG",
            "PEN(c:#{LINE_COLOR},w:{LINE_WIDTH}px)" AS OGR_STYLE
        FROM "{layer_name}"
    """
    gdal.VectorTranslate(
        destNameOrDestDS=str(OUTPUT_KML_TRAILHEADS),
        srcDS=str(INPUT_SHP_TRAILHEADS),
        format="KML",
        SQLDialect="SQLITE",
        SQLStatement=" ".join(sql.split()),
        layerName=LAYER_EXPORT_NAME_THS,
        dstSRS="EPSG:4326",
    )


def _flag(val: str | None) -> str:
    return "🟢" if _is_allowed_value(val) else "🔴"


def _first_or_none(el: ET.Element | None) -> str | None:
    if el is None or el.text is None:
        return None
    t = el.text.strip()
    return t if t else None


def _val(pm: ET.Element, field: str) -> str | None:
    return _find_simpledata_value(pm, field)


def _is_usfs_manager(val: str | None) -> bool:
    if not val:
        return False
    v = val.casefold()
    return ("usfs" in v) or ("forest service" in v) or ("national forest" in v)


def apply_icon_style(kml_path: Path, style_id: str, icon_color: str, icon_scale: str, label_color: str, label_scale: str) -> int:
    ET.register_namespace("", KML_NS)
    tree = ET.parse(kml_path)
    root = tree.getroot()
    doc = root.find("kml:Document", NS)
    if doc is None:
        return 0

    # Remove existing style with same id
    for s in doc.findall("kml:Style", NS):
        if s.get("id") == style_id:
            doc.remove(s)

    style_el = ET.Element("Style", {"id": style_id})
    icon_style = ET.SubElement(style_el, "IconStyle")
    color_el = ET.SubElement(icon_style, "color")
    color_el.text = icon_color
    scale_el = ET.SubElement(icon_style, "scale")
    scale_el.text = icon_scale
    icon_el = ET.SubElement(icon_style, "Icon")
    href_el = ET.SubElement(icon_el, "href")
    href_el.text = ""  # use default pushpin, tinted via color

    label_style = ET.SubElement(style_el, "LabelStyle")
    label_color_el = ET.SubElement(label_style, "color")
    label_color_el.text = label_color
    label_scale_el = ET.SubElement(label_style, "scale")
    label_scale_el.text = label_scale

    doc.insert(0, style_el)

    updated = 0
    for pm in doc.findall(".//kml:Placemark", NS):
        for s in pm.findall("kml:Style", NS):
            pm.remove(s)
        style_url = pm.find("kml:styleUrl", NS)
        if style_url is None:
            style_url = ET.Element("styleUrl")
            name_el = pm.find("kml:name", NS)
            idx = list(pm).index(name_el) + 1 if name_el is not None else 0
            pm.insert(idx, style_url)
        style_url.text = f"#{style_id}"
        updated += 1

    tree.write(kml_path, encoding="utf-8", xml_declaration=True)
    return updated


def inject_cotrex_description(kml_path: Path) -> int:
    ET.register_namespace("", KML_NS)
    tree = ET.parse(kml_path)
    root = tree.getroot()
    updated = 0

    def summary_row(label: str, value: str | None) -> str:
        if value is None or value == "":
            return ""
        return f"<tr><td><b>{label}</b></td><td>{value}</td></tr>"

    for pm in root.findall(".//{http://www.opengis.net/kml/2.2}Placemark"):
        # Quick summary table
        surface = _val(pm, "surface")
        length_mi = _val(pm, "length_mi_")
        manager = _val(pm, "manager")
        access = _val(pm, "access")
        url = _val(pm, "url")
        summary_rows = [
            summary_row("Surface", surface),
            summary_row("Length (mi)", length_mi),
            summary_row("Manager", manager),
            summary_row("Access", access),
            summary_row("URL", f'<a href="{url}">{url}</a>' if url else None),
        ]
        summary_table = f"<table>{''.join(r for r in summary_rows if r)}</table>"

        # Allowed/seasonal legend
        legend_defs = [
            ("Hiking", "hiking"),
            ("Horse", "horse"),
            ("Bike", "bike"),
            ("Motorcycle", "motorcycle"),
            ("ATV", "atv"),
            ("OHV > 50\"", "ohv_gt_50"),
            ("Highway vehicles", "highway_ve"),
            ("Dogs", "dogs"),
        ]
        legend_rows = "".join(
            f"<tr><td style=\"width:28px;text-align:center;\">{_flag(_val(pm, field))}</td>"
            f"<td>{label}</td>"
            f"<td style=\"white-space:nowrap;\">{(_val(pm, field) or '').strip()}</td></tr>"
            for label, field in legend_defs
        )
        legend_table = (
            "<table style=\"width:100%;\">"
            "<tr><th style=\"width:28px;\">Status</th><th>Use</th><th style=\"white-space:nowrap;\">Notes/Dates</th></tr>"
            f"{legend_rows}"
            "</table>"
        )

        # Full attribute dump (priority first)
        values: list[tuple[str, str]] = []
        for sd in pm.findall(".//{http://www.opengis.net/kml/2.2}SimpleData"):
            name = sd.get("name")
            val = (sd.text or "").strip()
            if not name or not val:
                continue
            values.append((name, val))

        if not values:
            continue

        priority = [
            "NAME",
            "NAME_LONG",
            "feature_id",
            "trail_num",
            "type",
            "surface",
            "length_mi_",
            "manager",
            "access",
            "hiking",
            "bike",
            "horse",
            "motorcycle",
            "atv",
            "ohv_gt_50",
            "highway_ve",
            "dogs",
            "seasonalit",
            "INPUT_DATE",
            "EDIT_DATE",
        ]
        rows: list[str] = []
        seen = set()
        for pname in priority:
            for name, val in values:
                if name == pname and name not in seen:
                    rows.append(f"<tr><td><b>{name}</b></td><td>{val}</td></tr>")
                    seen.add(name)
                    break
        for name, val in values:
            if name in seen:
                continue
            rows.append(f"<tr><td><b>{name}</b></td><td>{val}</td></tr>")
        full_table = f"<table>{''.join(rows)}</table>"

        html = f"{summary_table}<br/>{legend_table}<br/><br/>{full_table}"
        desc = pm.find("{http://www.opengis.net/kml/2.2}description")
        if desc is None:
            desc = ET.Element("description")
            pm.insert(1, desc)
        desc.text = _CDATA(html)
        updated += 1

    tree.write(kml_path, encoding="utf-8", xml_declaration=True)
    return updated


def embed_label_points_wgs84(shp_path: str, kml_path: str, label_fields: list[str]) -> int:
    """
    Embed a Point into each Placemark geometry (MultiGeometry) so ATAK renders labels.
    Shapefile is reprojected from its native CRS to WGS84 for the centroid.
    """
    ds = ogr.Open(shp_path)
    if ds is None or ds.GetLayerCount() == 0:
        raise RuntimeError("Could not open shapefile to embed label points.")
    layer = ds.GetLayer(0)
    src_srs = layer.GetSpatialRef()
    if src_srs is None:
        raise RuntimeError("Shapefile missing spatial reference.")
    dst_srs = osr.SpatialReference()
    dst_srs.ImportFromEPSG(4326)
    transform = osr.CoordinateTransformation(src_srs, dst_srs)

    centroids: dict[str, tuple[float, float]] = {}
    for feat in layer:
        obj_id = feat.GetField("OBJECTID")
        manager_val = feat.GetField("manager")
        if manager_val and _is_usfs_manager(str(manager_val)):
            continue
        geom = feat.GetGeometryRef()
        if obj_id is None or geom is None or geom.IsEmpty():
            continue
        try:
            pt = geom.Centroid()
            if pt is None or pt.IsEmpty():
                continue
            pt.Transform(transform)
            centroids[str(obj_id)] = (pt.GetX(), pt.GetY())
        except RuntimeError:
            continue

    ET.register_namespace("", KML_NS)
    tree = ET.parse(kml_path)
    root = tree.getroot()

    updated = 0
    for pm in root.findall(".//{http://www.opengis.net/kml/2.2}Placemark"):
        obj_id = _find_simpledata_value(pm, "OBJECTID")
        xy = centroids.get(obj_id) if obj_id else None
        if xy is None:
            continue

        geom_children = [
            child
            for child in list(pm)
            if child.tag in {
                "{http://www.opengis.net/kml/2.2}LineString",
                "{http://www.opengis.net/kml/2.2}MultiGeometry",
                "{http://www.opengis.net/kml/2.2}Polygon",
                "{http://www.opengis.net/kml/2.2}Point",
            }
        ]
        if not geom_children:
            continue

        if len(geom_children) == 1 and geom_children[0].tag.endswith("MultiGeometry"):
            mg = geom_children[0]
        else:
            mg = ET.Element("MultiGeometry")
            for child in geom_children:
                pm.remove(child)
                mg.append(child)
            pm.append(mg)

        point_el = ET.Element("Point")
        alt_mode_el = ET.SubElement(point_el, "altitudeMode")
        alt_mode_el.text = "clampToGround"
        coords_el = ET.SubElement(point_el, "coordinates")
        coords_el.text = f"{xy[0]},{xy[1]},0"
        mg.append(point_el)
        updated += 1

    tree.write(kml_path, encoding="utf-8", xml_declaration=True)
    return updated


def inject_trailhead_description(kml_path: Path) -> int:
    ET.register_namespace("", KML_NS)
    tree = ET.parse(kml_path)
    root = tree.getroot()
    updated = 0

    def summary_row(label: str, value: str | None) -> str:
        if value is None or value == "":
            return ""
        return f"<tr><td><b>{label}</b></td><td>{value}</td></tr>"

    for pm in root.findall(".//kml:Placemark", NS):
        name = _val(pm, "NAME") or _val(pm, "name")
        alt_name = _val(pm, "alt_name")
        typ = _val(pm, "type")
        manager = _val(pm, "manager")
        winter = _val(pm, "winter_act")

        legend_defs = [
            ("Bathrooms", "bathrooms"),
            ("Water", "water"),
            ("Fee", "fee"),
        ]
        legend_rows = "".join(
            f"<tr><td style=\"width:28px;text-align:center;\">{_flag(_val(pm, field))}</td>"
            f"<td>{label}</td>"
            f"<td style=\"white-space:nowrap;\">{(_val(pm, field) or '').strip()}</td></tr>"
            for label, field in legend_defs
        )
        legend_table = (
            "<table style=\"width:100%;\">"
            "<tr><th style=\"width:28px;\">Status</th><th>Facility</th><th style=\"white-space:nowrap;\">Details</th></tr>"
            f"{legend_rows}"
            "</table>"
        )

        summary_rows = [
            summary_row("Name", name),
            summary_row("Alt name", alt_name),
            summary_row("Type", typ),
            summary_row("Manager", manager),
            summary_row("Winter activity", winter),
        ]
        summary_table = f"<table>{''.join(r for r in summary_rows if r)}</table>"

        values: list[tuple[str, str]] = []
        for sd in pm.findall(".//kml:SimpleData", NS):
            fname = sd.get("name")
            val = (sd.text or "").strip()
            if not fname or not val:
                continue
            values.append((fname, val))
        if not values:
            continue

        priority = ["NAME", "NAME_LONG", "name", "alt_name", "type", "manager", "bathrooms", "water", "fee", "winter_act", "INPUT_DATE", "EDIT_DATE"]
        rows: list[str] = []
        seen = set()
        for pname in priority:
            for fname, val in values:
                if fname == pname and fname not in seen:
                    rows.append(f"<tr><td><b>{fname}</b></td><td>{val}</td></tr>")
                    seen.add(fname)
                    break
        for fname, val in values:
            if fname in seen:
                continue
            rows.append(f"<tr><td><b>{fname}</b></td><td>{val}</td></tr>")
        full_table = f"<table>{''.join(rows)}</table>"

        html = f"{summary_table}<br/>{legend_table}<br/><br/>{full_table}"
        desc = pm.find("kml:description", NS)
        if desc is None:
            desc = ET.Element("description")
            pm.insert(1, desc)
        desc.text = _CDATA(html)
        updated += 1

    tree.write(kml_path, encoding="utf-8", xml_declaration=True)
    return updated


def split_into_use_layers(kml_path: Path) -> int:
    """
    Rebuild the KML Document into per-use folders (Hiking, Bike, ATV, etc.).
    Features appear in every folder whose use flag is allowed.
    """
    ET.register_namespace("", KML_NS)
    tree = ET.parse(kml_path)
    root = tree.getroot()
    doc = root.find("kml:Document", NS)
    if doc is None:
        return 0

    doc_name = _first_or_none(doc.find("kml:name", NS))
    schemas = [deepcopy(s) for s in doc.findall("kml:Schema", NS)]
    placemarks = doc.findall(".//kml:Placemark", NS)

    k = lambda tag: f"{{{KML_NS}}}{tag}"
    created = 0

    for cat_name, field, color, slug in CATEGORIES:
        # Build a fresh KML document for this category.
        root_cat = ET.Element(k("kml"))
        doc_cat = ET.SubElement(root_cat, k("Document"))
        name_el = ET.SubElement(doc_cat, k("name"))
        name_el.text = f"{doc_name or 'COTREX Trails'} — {cat_name}"
        for s in schemas:
            doc_cat.append(deepcopy(s))

        # Shared style per category.
        style = ET.SubElement(doc_cat, k("Style"), {"id": "catStyle"})
        ls = ET.SubElement(style, k("LineStyle"))
        c = ET.SubElement(ls, k("color"))
        c.text = color
        w = ET.SubElement(ls, k("width"))
        w.text = LINE_WIDTH

        count = 0
        for pm in placemarks:
            if not _is_allowed_value(_find_simpledata_value(pm, field)):
                continue
            pm_copy = deepcopy(pm)
            # Remove existing styles and point to shared style.
            for s in pm_copy.findall("kml:Style", NS):
                pm_copy.remove(s)
            for s in pm_copy.findall("kml:styleUrl", NS):
                pm_copy.remove(s)
            style_url = ET.Element(k("styleUrl"))
            style_url.text = "#catStyle"
            name_el_pm = pm_copy.find("kml:name", NS)
            insert_idx = list(pm_copy).index(name_el_pm) + 1 if name_el_pm is not None else 0
            pm_copy.insert(insert_idx, style_url)
            doc_cat.append(pm_copy)
            count += 1

        if count == 0:
            continue

        out_kml = OUTPUT_DIR / f"COTREX_Trails_{slug}.kml"
        out_kmz = OUTPUT_DIR / f"COTREX_Trails_{slug}.kmz"
        ET.ElementTree(root_cat).write(out_kml, encoding="utf-8", xml_declaration=True)
        make_kmz(str(out_kml), str(out_kmz), extra_files=None)
        created += 1
        print(f"Wrote {out_kml} (features: {count})")
        print(f"Wrote {out_kmz}")

    return created


def main() -> int:
    if not INPUT_SHP.exists():
        print(f"ERROR: missing shapefile: {INPUT_SHP}", file=sys.stderr)
        return 2
    if not INPUT_SHP_TRAILHEADS.exists():
        print(f"ERROR: missing trailheads shapefile: {INPUT_SHP_TRAILHEADS}", file=sys.stderr)
        return 2

    export_to_kml()
    ensure_placemark_names(str(OUTPUT_KML), ["NAME", "NAME_LONG", "feature_id", "name", "trail_num"], overwrite=True)
    embed_label_points_wgs84(str(INPUT_SHP), str(OUTPUT_KML), ["NAME", "NAME_LONG"])
    colorize_lines_by_access(str(OUTPUT_KML), ALLOW_FIELDS, color_allowed="ffcc66ff", color_denied="ff7f7f7f", width=LINE_WIDTH)
    inject_cotrex_description(OUTPUT_KML)
    duplicate_simpledata_to_data(str(OUTPUT_KML))
    make_kmz(str(OUTPUT_KML), str(OUTPUT_KMZ), extra_files=None)
    print(f"Wrote {OUTPUT_KML}")
    print(f"Wrote {OUTPUT_KMZ}")
    split_into_use_layers(OUTPUT_KML)

    # Trailheads export (no USFS filter).
    export_trailheads_to_kml()
    ensure_placemark_names(str(OUTPUT_KML_TRAILHEADS), ["NAME", "name", "alt_name", "feature_id"], overwrite=True)
    inject_trailhead_description(OUTPUT_KML_TRAILHEADS)
    duplicate_simpledata_to_data(str(OUTPUT_KML_TRAILHEADS))
    apply_icon_style(OUTPUT_KML_TRAILHEADS, style_id="TrailheadStyle", icon_color=ICON_COLOR, icon_scale=ICON_SCALE, label_color=LABEL_COLOR, label_scale=LABEL_SCALE)
    make_kmz(str(OUTPUT_KML_TRAILHEADS), str(OUTPUT_KMZ_TRAILHEADS), extra_files=None)
    print(f"Wrote {OUTPUT_KML_TRAILHEADS}")
    print(f"Wrote {OUTPUT_KMZ_TRAILHEADS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
