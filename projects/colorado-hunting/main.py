#!/usr/bin/env python3

from pathlib import Path
import sys
import xml.etree.ElementTree as ET

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
# CONSTANTS / NAMESPACES
# ---------------------------
KML_NS = "http://www.opengis.net/kml/2.2"
NS = {"kml": KML_NS}

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
LAND_URL = (
    "ESRIJSON:"
    "https://services3.arcgis.com/unh8qj8OkZd7wlfi/arcgis/rest/services/"
    "MS_COMaP_v20211005/FeatureServer/0/query?where=1%3D1&outFields=*&f=json"
)
LAND_LAYER_NAME = "ESRIJSON"
LAND_LABEL_FIELDS: list[str] = ["NAME", "OWNER", "legend"]
LAND_STATUS_COLORS: dict[str, dict[str, str]] = {
    "public": {"poly": "5500ff00", "line": "ff3d8a0e", "icon": "ff33cc33"},
    "caution": {"poly": "6607c1ff", "line": "ff007cc2", "icon": "ff07c1ff"},
    "private": {"poly": "550000ff", "line": "ff0000ff", "icon": "ff0000ff"},
}
LAND_PRIORITY_FIELDS: list[str] = [
    "NAME",
    "OWNER",
    "MANAGER",
    "PUBLIC_ACCESS",
    "MGMT_DESCRIPTION",
    "PROTECTION_MECHANISM",
    "PROTECTION_TERM",
    "EASEMENT_HOLDER",
    "ACRES",
    "legend",
]


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


def _find_simpledata_value(pm: ET.Element, field_name: str) -> str | None:
    for sd in pm.findall(".//kml:SimpleData", NS):
        if sd.get("name") == field_name and sd.text:
            v = sd.text.strip()
            if v:
                return v
    return None


def _strip_cdata(text: str | None) -> str:
    if not text:
        return ""
    if text.startswith("<![CDATA[") and text.endswith("]]>"):
        return text[9:-3]
    return text


def _classify_land_status(legend: str | None, public_access: str | None) -> str:
    lg = (legend or "").strip().lower()
    access = (public_access or "").strip().lower()
    public_legends = {
        "blm",
        "federal",
        "nps",
        "usfs",
        "usfws",
        "tribal",
        "state",
        "local",
    }
    caution_legends = {
        "ngo/land trust",
        "private conservation",
    }
    if lg in {"private"}:
        return "private"
    status = "public" if lg in public_legends else "caution"
    if lg in caution_legends:
        status = "caution"
    if status == "public" and access not in {"yes", "open", "public"}:
        status = "caution"
    return status


def _apply_land_styles(kml_path: Path) -> int:
    ET.register_namespace("", KML_NS)
    tree = ET.parse(kml_path)
    root = tree.getroot()
    updated = 0

    for pm in root.findall(".//kml:Placemark", NS):
        legend_val = _find_simpledata_value(pm, "legend")
        access_val = _find_simpledata_value(pm, "PUBLIC_ACCESS")
        status = _classify_land_status(legend_val, access_val)
        colors = LAND_STATUS_COLORS[status]

        style = pm.find("kml:Style", NS)
        if style is None:
            style = ET.Element("Style")
            pm.insert(0, style)

        # Polygon + outline styling.
        poly = style.find("kml:PolyStyle", NS)
        if poly is None:
            poly = ET.Element("PolyStyle")
            style.append(poly)
        poly_color = poly.find("kml:color", NS)
        if poly_color is None:
            poly_color = ET.Element("color")
            poly.append(poly_color)
        poly_color.text = colors["poly"]
        for tag, val in (("fill", "1"), ("outline", "1")):
            child = poly.find(f"kml:{tag}", NS)
            if child is None:
                child = ET.Element(tag)
                poly.append(child)
            child.text = val

        line = style.find("kml:LineStyle", NS)
        if line is None:
            line = ET.Element("LineStyle")
            style.append(line)
        line_color = line.find("kml:color", NS)
        if line_color is None:
            line_color = ET.Element("color")
            line.append(line_color)
        line_color.text = colors["line"]
        line_width = line.find("kml:width", NS)
        if line_width is None:
            line_width = ET.Element("width")
            line.append(line_width)
        line_width.text = LINE_WIDTH

        # Icon to give a quick green/yellow/red dot in clients that render icons for polygons.
        icon = style.find("kml:IconStyle", NS)
        if icon is None:
            icon = ET.Element("IconStyle")
            style.insert(0, icon)
        icon_color = icon.find("kml:color", NS)
        if icon_color is None:
            icon_color = ET.Element("color")
            icon.append(icon_color)
        icon_color.text = colors["icon"]
        icon_scale = icon.find("kml:scale", NS)
        if icon_scale is None:
            icon_scale = ET.Element("scale")
            icon.append(icon_scale)
        icon_scale.text = "0.9"

        # Add a short status banner ahead of the metadata table.
        desc = pm.find("kml:description", NS)
        body_html = _strip_cdata(desc.text if desc is not None else "")
        status_label = {
            "public": "🟢 Public",
            "caution": "🟡 Check access/terms",
            "private": "🔴 Private / limited",
        }[status]
        legend_label = legend_val or "Unknown ownership"
        access_label = f"Access: {access_val}" if access_val else ""
        header = f"<div><b>{status_label}</b> — {legend_label}</div>"
        if access_label:
            header += f"<div>{access_label}</div>"
        new_html = f"{header}<br/>{body_html}" if body_html else header
        if desc is None:
            desc = ET.Element("description")
            pm.insert(1, desc)
        desc.text = f"<![CDATA[{new_html}]]>"
        updated += 1

    tree.write(kml_path, encoding="utf-8", xml_declaration=True)
    return updated


def export_land_ownership() -> tuple[Path, Path]:
    out_kml = OUTPUT_DIR / "CO_Land_Ownership.kml"
    sql = f"""
        SELECT
            *,
            COALESCE(NAME, OWNER, legend) AS NAME,
            "PEN(c:#ff646464,w:{LINE_WIDTH}px);BRUSH(fc:#33ffffff)" AS OGR_STYLE
        FROM "{LAND_LAYER_NAME}"
    """
    vector_translate_to_kml(
        shp_path=LAND_URL,
        out_kml=str(out_kml),
        sql_statement=sql,
        export_layer_name="co_land_ownership",
        spat_filter=None,
    )

    ensure_placemark_names(out_kml, LAND_LABEL_FIELDS, overwrite=True)
    inject_labelstyle(out_kml, label_color="ff1f1f1f", label_scale="11.0")
    inject_generic_description_table(
        out_kml, priority_fields=LAND_PRIORITY_FIELDS, heading="Land Ownership (COMaP)"
    )
    _apply_land_styles(out_kml)
    out_kmz = OUTPUT_DIR / "CO_Land_Ownership.kmz"
    make_kmz(out_kml, out_kmz, extra_files=None)
    delete_kmls([out_kml])
    return out_kml, out_kmz


def main() -> int:
    trails_shp = INPUT_SHP
    if not trails_shp.exists():
        print(f"ERROR: GMU shapefile not found: {trails_shp}", file=sys.stderr)
        return 2

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    gmu_result = export_gmu(trails_shp)
    land_result = export_land_ownership()

    if not gmu_result:
        print("No GMU export produced.")
        return 3

    print(f"Created GMU KMZ in {OUTPUT_DIR}")
    print(f"Created land ownership KMZ in {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
