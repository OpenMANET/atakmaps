#!/usr/bin/env python3

import copy
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from osgeo import gdal, ogr  # GDAL/OGR Python bindings

gdal.UseExceptions()
ogr.UseExceptions()

# Support CDATA serialization in ElementTree.
class _CDATA(str):
    pass


def _serialize_xml(write, elem, qnames, namespaces, short_empty_elements=True):
    tag = elem.tag
    text = elem.text
    if tag is ET.Comment:
        write("<!--%s-->" % ET._escape_cdata(text))
    elif tag is ET.ProcessingInstruction:
        write("<?%s?>" % ET._escape_cdata(text))
    else:
        write("<" + qnames[tag])
        for k, v in elem.items():
            write(" %s=\"%s\"" % (qnames[k], ET._escape_attrib(v)))
        if text or len(elem):
            write(">")
            if isinstance(text, _CDATA):
                write(f"<![CDATA[{text}]]>")
            elif text:
                write(ET._escape_cdata(text))
            for e in elem:
                _serialize_xml(write, e, qnames, namespaces, short_empty_elements)
            write("</" + qnames[tag] + ">")
        else:
            write(" />")


# Monkeypatch ElementTree to use CDATA handler above.
ET._original_serialize_xml = ET._serialize_xml
ET._serialize_xml = _serialize_xml

KML_NS = "http://www.opengis.net/kml/2.2"
GX_NS = "http://www.google.com/kml/ext/2.2"
NS = {"kml": KML_NS, "gx": GX_NS}


def get_layer_name(shp_path: str) -> str:
    ds = ogr.Open(shp_path)
    if ds is None or ds.GetLayerCount() == 0:
        raise RuntimeError("Could not open shapefile to read layer name.")
    return ds.GetLayer(0).GetName()


def _get_kml_driver() -> ogr.Driver:
    for name in ("LIBKML", "KML"):
        drv = ogr.GetDriverByName(name)
        if drv is not None:
            return drv
    raise RuntimeError("No KML/LIBKML driver available in GDAL.")


def run_export_with_gdal(
    shp_path: str,
    out_kml: str,
    layer_name: str,
    spat_filter: tuple[float, float, float, float] | None,
    export_layer_name: str,
    line_color: str,
    line_width: str,
) -> None:
    """
    VectorTranslate mirrors the ogr2ogr call via GDAL Python bindings.
    We duplicate NAME into Name_LONG so the original attribute survives
    even though KML uses <name> for labeling.
    """
    sql = (
        f'SELECT *, NAME AS "NAME_LONG", "PEN(c:#{line_color},w:{line_width}px)" AS OGR_STYLE '
        f'FROM "{layer_name}"'
    )
    vector_translate_to_kml(
        shp_path=shp_path,
        out_kml=out_kml,
        sql_statement=sql,
        export_layer_name=export_layer_name,
        spat_filter=spat_filter,
    )


def vector_translate_to_kml(
    shp_path: str,
    out_kml: str,
    sql_statement: str,
    export_layer_name: str,
    spat_filter: tuple[float, float, float, float] | None = None,
) -> None:
    """Generic KML export helper with caller-provided SQL."""
    Path(out_kml).unlink(missing_ok=True)
    _get_kml_driver()  # ensure driver exists early
    print(f"Exporting to KML via GDAL (layer: {export_layer_name})...")
    gdal.VectorTranslate(
        destNameOrDestDS=out_kml,
        srcDS=shp_path,
        format="KML",
        SQLDialect="SQLITE",
        SQLStatement=sql_statement,
        layerName=export_layer_name,
        spatFilter=spat_filter,
    )
    print("KML export complete.")


def has_features(shp_path: Path, bbox: tuple[float, float, float, float] | None) -> bool:
    """Return True if the shapefile has at least one feature within an optional bbox."""
    ds = ogr.Open(str(shp_path))
    if ds is None or ds.GetLayerCount() == 0:
        return False
    layer = ds.GetLayer(0)
    if bbox:
        layer.SetSpatialFilterRect(*bbox)
    count = layer.GetFeatureCount()
    layer.SetSpatialFilter(None)
    return count > 0


def delete_kmls(paths: list[Path]) -> None:
    """Remove any KML/KMZ files in the provided iterable."""
    for p in {Path(path) for path in paths if path}:
        p.unlink(missing_ok=True)


def _find_simpledata_value(placemark: ET.Element, field_name: str) -> str | None:
    """
    Look for:
      <ExtendedData><SchemaData><SimpleData name="FIELD">value</SimpleData>
    """
    for sd in placemark.findall(".//kml:SimpleData", NS):
        if sd.get("name") == field_name and (sd.text is not None):
            v = sd.text.strip()
            if v:
                return v
    return None


def _is_allowed_value(val: str | None) -> bool:
    if val is None:
        return False
    v = val.strip().lower()
    return v not in {"", "no", "closed", "n/a", "na", "none", "0"}


def ensure_placemark_names(kml_path: str, field_names: list[str], overwrite: bool = False) -> int:
    """
    Ensure each Placemark has a <name> value (ATAK label text source),
    using the first non-empty SimpleData field from ExtendedData.
    If overwrite=True, existing names are replaced using the same logic.
    """
    field_names = list(field_names)
    ET.register_namespace("", KML_NS)
    tree = ET.parse(kml_path)
    root = tree.getroot()

    changed = 0
    for pm in root.findall(".//kml:Placemark", NS):
        name_el = pm.find("kml:name", NS)
        current = (name_el.text.strip() if (name_el is not None and name_el.text) else "")

        if current and not overwrite:
            continue  # already has a name and we are preserving

        v = None
        for field_name in field_names:
            v = _find_simpledata_value(pm, field_name)
            if v:
                break

        if not v:
            continue  # can't populate with any configured field

        if name_el is None:
            # Insert name as the first child (nice and KML-common)
            name_el = ET.Element("name")
            pm.insert(0, name_el)

        name_el.text = v
        changed += 1

    tree.write(kml_path, encoding="utf-8", xml_declaration=True)
    return changed


def inject_labelstyle(kml_path: str, label_color: str, label_scale: str) -> int:
    ET.register_namespace("", KML_NS)
    tree = ET.parse(kml_path)
    root = tree.getroot()

    changed = 0
    for style in root.findall(".//kml:Style", NS):
        if style.find("kml:LabelStyle", NS) is not None:
            continue

        label_style = ET.Element("LabelStyle")
        c = ET.SubElement(label_style, "color")
        c.text = label_color
        s = ET.SubElement(label_style, "scale")
        s.text = label_scale

        line_style = style.find("kml:LineStyle", NS)
        if line_style is not None:
            idx = list(style).index(line_style)
            style.insert(idx, label_style)
        else:
            style.append(label_style)

        changed += 1

    tree.write(kml_path, encoding="utf-8", xml_declaration=True)
    return changed


def apply_atak_style_and_region(
    kml_path: str,
    style_id: str,
    icon_href: str | None,
    icon_scale: str,
    poly_color: str,
    poly_outline: str,
    label_color: str,
    label_scale: str,
    line_color: str,
    line_width: str,
    region: dict[str, float] | None = None,
) -> tuple[int, bool]:
    """
    Inject a single Document-level Style (with IconStyle/LabelStyle/PolyStyle)
    and re-point all placemarks to it via <styleUrl>. Optionally attach a
    Document-level <Region> element (ATAK uses this for LOD/bounds).
    Returns (placemarks_updated, region_added_flag).
    """
    ET.register_namespace("", KML_NS)
    ET.register_namespace("gx", GX_NS)
    tree = ET.parse(kml_path)
    root = tree.getroot()

    doc = root.find("kml:Document", NS)
    if doc is None:
        raise RuntimeError("KML missing <Document> element.")

    # Remove any existing style with the same ID to avoid duplicates
    for existing_style in doc.findall("kml:Style", NS):
        if existing_style.get("id") == style_id:
            doc.remove(existing_style)

    style_el = ET.Element("Style", {"id": style_id})

    if icon_href:
        icon_style = ET.SubElement(style_el, "IconStyle")
        icon_scale_el = ET.SubElement(icon_style, "scale")
        icon_scale_el.text = icon_scale
        icon_el = ET.SubElement(icon_style, "Icon")
        icon_href_el = ET.SubElement(icon_el, "href")
        icon_href_el.text = icon_href

    label_style = ET.SubElement(style_el, "LabelStyle")
    label_color_el = ET.SubElement(label_style, "color")
    label_color_el.text = label_color
    label_scale_el = ET.SubElement(label_style, "scale")
    label_scale_el.text = label_scale
    # Force label rendering in clients honoring gx extensions (e.g., ATAK).
    gx_label_vis = ET.SubElement(style_el, f"{{{GX_NS}}}labelVisibility")
    gx_label_vis.text = "1"

    poly_style = ET.SubElement(style_el, "PolyStyle")
    poly_color_el = ET.SubElement(poly_style, "color")
    poly_color_el.text = poly_color
    poly_outline_el = ET.SubElement(poly_style, "outline")
    poly_outline_el.text = poly_outline

    # Keep line styling so the trail lines retain their color/width.
    line_style = ET.SubElement(style_el, "LineStyle")
    line_color_el = ET.SubElement(line_style, "color")
    line_color_el.text = line_color
    line_width_el = ET.SubElement(line_style, "width")
    line_width_el.text = line_width

    # Insert the style near the top (after Schema if present)
    doc_children = list(doc)
    insert_idx = 1 if doc_children and doc_children[0].tag.endswith("Schema") else 0
    doc.insert(insert_idx, style_el)

    # Point each placemark at the shared style and remove inline styles
    updated = 0
    for pm in doc.findall(".//kml:Placemark", NS):
        for inline_style in pm.findall("kml:Style", NS):
            pm.remove(inline_style)

        style_url = pm.find("kml:styleUrl", NS)
        if style_url is None:
            style_url = ET.Element("styleUrl")
            name_el = pm.find("kml:name", NS)
            idx = list(pm).index(name_el) + 1 if name_el is not None else 0
            pm.insert(idx, style_url)

        new_url = f"#{style_id}"
        if style_url.text != new_url:
            style_url.text = new_url
            updated += 1

        # Some clients (ATAK) ignore gx:labelVisibility on shared styles for
        # line features; force it directly on each Placemark instead.
        label_vis = pm.find("gx:labelVisibility", NS)
        if label_vis is None:
            label_vis = ET.Element(f"{{{GX_NS}}}labelVisibility")
            # Prefer to insert right after styleUrl/name so it sits with styling.
            insert_after = style_url if style_url is not None else pm.find("kml:name", NS)
            if insert_after is not None:
                idx = list(pm).index(insert_after)
                pm.insert(idx + 1, label_vis)
            else:
                pm.insert(0, label_vis)
        label_vis.text = "1"

    region_added = False
    if region:
        # Remove existing Region blocks to avoid conflicting bounds
        for reg in doc.findall("kml:Region", NS):
            doc.remove(reg)

        region_el = ET.Element("Region")
        latlon = ET.SubElement(region_el, "LatLonAltBox")
        for key in ("west", "south", "east", "north"):
            child = ET.SubElement(latlon, key)
            child.text = str(region[key])
        lod = ET.SubElement(region_el, "Lod")
        minlod = ET.SubElement(lod, "minLodPixels")
        minlod.text = str(region["min_lod_pixels"])
        # Insert the region after the shared style if present, otherwise at front.
        try:
            style_pos = list(doc).index(style_el)
            doc.insert(style_pos + 1, region_el)
        except ValueError:
            doc.insert(0, region_el)
        region_added = True

    tree.write(kml_path, encoding="utf-8", xml_declaration=True)
    return updated, region_added


def _get_field_value(feat: ogr.Feature, field_name: str) -> str | None:
    """Return a trimmed string field value if present and non-empty."""
    if feat is None:
        return None
    idx = feat.GetFieldIndex(field_name)
    if idx == -1:
        return None
    val = feat.GetField(idx)
    if val is None:
        return None
    text = str(val).strip()
    return text if text else None


def add_point_label_folder_from_lines(
    shp_path: str,
    kml_path: str,
    folder_name: str,
    style_id: str,
    label_fields: list[str],
    schema_id: str,
) -> int:
    """
    Create a Folder of point placemarks (midpoints of each line feature) so ATAK
    can display labels that would otherwise be ignored for LineStrings.
    Returns the number of point placemarks added.
    """
    ds = ogr.Open(shp_path)
    if ds is None or ds.GetLayerCount() == 0:
        raise RuntimeError("Could not open shapefile to build label points.")
    layer = ds.GetLayer(0)

    ET.register_namespace("", KML_NS)
    ET.register_namespace("gx", GX_NS)
    tree = ET.parse(kml_path)
    root = tree.getroot()

    doc = root.find("kml:Document", NS)
    if doc is None:
        raise RuntimeError("KML missing <Document> element.")

    folder_el = ET.Element("Folder")
    folder_name_el = ET.SubElement(folder_el, "name")
    folder_name_el.text = folder_name

    added = 0
    defn = layer.GetLayerDefn()
    for feat in layer:
        geom = feat.GetGeometryRef()
        if geom is None or geom.IsEmpty():
            continue

        try:
            pt = geom.Centroid()
        except RuntimeError:
            continue

        if pt is None or pt.IsEmpty():
            continue

        label_val = None
        for fld in list(label_fields) + ["NAME"]:
            label_val = _get_field_value(feat, fld)
            if label_val:
                break

        if not label_val:
            continue

        pm = ET.Element("Placemark")
        name_el = ET.SubElement(pm, "name")
        name_el.text = label_val

        style_url = ET.SubElement(pm, "styleUrl")
        style_url.text = f"#{style_id}"
        gx_label_vis = ET.SubElement(pm, f"{{{GX_NS}}}labelVisibility")
        gx_label_vis.text = "1"

        ext = ET.SubElement(pm, "ExtendedData")
        sd_container = ET.SubElement(ext, "SchemaData", {"schemaUrl": f"#{schema_id}"})
        for i in range(defn.GetFieldCount()):
            fname = defn.GetFieldDefn(i).GetName()
            val = feat.GetField(i)
            if val is None:
                continue
            sd = ET.SubElement(sd_container, "SimpleData", {"name": fname})
            sd.text = str(val)

        point_el = ET.SubElement(pm, "Point")
        extrude_el = ET.SubElement(point_el, "extrude")
        extrude_el.text = "0"
        alt_mode_el = ET.SubElement(point_el, "altitudeMode")
        alt_mode_el.text = "clampToGround"
        coords_el = ET.SubElement(point_el, "coordinates")
        coords_el.text = f"{pt.GetX()},{pt.GetY()},0"

        folder_el.append(pm)
        added += 1

    # Append folder near the end of Document to keep organization simple.
    doc.append(folder_el)

    tree.write(kml_path, encoding="utf-8", xml_declaration=True)
    return added


def colorize_lines_by_access(
    kml_path: str,
    allow_fields: list[str],
    color_allowed: str,
    color_denied: str,
    width: str,
) -> int:
    """
    Attach an inline Style to each Placemark with a LineString/MultiGeometry,
    coloring green if any allow_field is truthy (not 'no/closed/etc'), else red.
    """
    ET.register_namespace("", KML_NS)
    tree = ET.parse(kml_path)
    root = tree.getroot()
    updated = 0
    for pm in root.findall(".//kml:Placemark", NS):
        # Only apply to placemarks with line geometry
        if pm.find(".//kml:LineString", NS) is None:
            continue
        allowed = False
        for fld in allow_fields:
            if _is_allowed_value(_find_simpledata_value(pm, fld)):
                allowed = True
                break
        # Remove existing inline styles to avoid duplicates
        for s in pm.findall("kml:Style", NS):
            pm.remove(s)
        style_el = ET.Element("Style")
        ls = ET.SubElement(style_el, "LineStyle")
        c = ET.SubElement(ls, "color")
        c.text = color_allowed if allowed else color_denied
        w = ET.SubElement(ls, "width")
        w.text = width
        # Insert style near the top (after name if present)
        name_el = pm.find("kml:name", NS)
        if name_el is not None:
            idx = list(pm).index(name_el)
            pm.insert(idx + 1, style_el)
        else:
            pm.insert(0, style_el)
        updated += 1

    # Re-wrap descriptions in CDATA so HTML is not escaped after this write.
    for desc in root.findall(".//kml:description", NS):
        if desc.text:
            desc.text = _CDATA(desc.text)

    tree.write(kml_path, encoding="utf-8", xml_declaration=True)
    return updated


def embed_label_points_in_multigeometry(
    shp_path: str,
    kml_path: str,
    label_fields: list[str],
) -> int:
    """
    Add a Point (centroid) into each Placemark geometry as part of a
    MultiGeometry so ATAK treats the Placemark like a point for labeling while
    retaining the original line geometry.
    Returns the number of placemarks updated.
    """
    ds = ogr.Open(shp_path)
    if ds is None or ds.GetLayerCount() == 0:
        raise RuntimeError("Could not open shapefile to embed label points.")
    layer = ds.GetLayer(0)
    layer.ResetReading()

    # Precompute centroids keyed by OBJECTID for reliable lookup.
    centroids: dict[str, tuple[float, float]] = {}
    for feat in layer:
        obj_id = feat.GetField("OBJECTID")
        geom = feat.GetGeometryRef()
        if obj_id is None or geom is None or geom.IsEmpty():
            continue
        try:
            pt = geom.Centroid()
        except RuntimeError:
            continue
        if pt is None or pt.IsEmpty():
            continue
        centroids[str(obj_id)] = (pt.GetX(), pt.GetY())

    ET.register_namespace("", KML_NS)
    ET.register_namespace("gx", GX_NS)
    tree = ET.parse(kml_path)
    root = tree.getroot()
    placemarks = root.findall(".//kml:Placemark", NS)

    updated = 0
    for pm in placemarks:
        obj_id = _find_simpledata_value(pm, "OBJECTID")
        xy = centroids.get(obj_id) if obj_id else None
        if xy is None:
            continue

        # Find existing geometry elements in the Placemark.
        geom_children = [
            child for child in list(pm)
            if child.tag in {
                f"{{{KML_NS}}}LineString",
                f"{{{KML_NS}}}MultiGeometry",
                f"{{{KML_NS}}}Polygon",
                f"{{{KML_NS}}}Point",
            }
        ]
        if not geom_children:
            continue

        # If already MultiGeometry, reuse; otherwise wrap existing geometries.
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


def duplicate_simpledata_to_data(kml_path: str) -> int:
    """
    Some clients (ATAK) surface <ExtendedData><Data> but ignore
    <ExtendedData><SchemaData><SimpleData>. Duplicate all SimpleData into
    <Data><displayName><value> entries so attribute metadata is visible in ATAK.
    Returns number of placemarks updated.
    """
    ET.register_namespace("", KML_NS)
    tree = ET.parse(kml_path)
    root = tree.getroot()
    updated = 0
    for pm in root.findall(".//kml:Placemark", NS):
        ext = pm.find("kml:ExtendedData", NS)
        if ext is None:
            continue
        existing_data = {(d.get("name"), (d.find("value").text if d.find("value") is not None else ""))
                         for d in ext.findall("kml:Data", NS)}
        added_any = False
        for sd in ext.findall(".//kml:SimpleData", NS):
            name = sd.get("name")
            val = (sd.text or "").strip()
            key = (name, val)
            if not name or key in existing_data:
                continue
            d = ET.Element("Data", {"name": name})
            dn = ET.SubElement(d, "displayName")
            dn.text = name
            v = ET.SubElement(d, "value")
            v.text = val
            ext.append(d)
            added_any = True
        if added_any:
            updated += 1
    tree.write(kml_path, encoding="utf-8", xml_declaration=True)
    return updated


def inject_description_from_simpledata(kml_path: str) -> int:
    """
    Build an HTML table in <description> from SimpleData fields so metadata
    appears in clients that ignore ExtendedData (ATAK tooltip/detail).
    """
    ET.register_namespace("", KML_NS)
    tree = ET.parse(kml_path)
    root = tree.getroot()
    updated = 0
    for pm in root.findall(".//kml:Placemark", NS):
        ext = pm.find("kml:ExtendedData", NS)
        if ext is None:
            continue
        lines = []
        for sd in ext.findall(".//kml:SimpleData", NS):
            name = sd.get("name")
            val = (sd.text or "").strip()
            if not name or val == "":
                continue
            lines.append(f"{name}: {val}")
        if not lines:
            continue
        html = "<br/>".join(lines)
        desc = pm.find("kml:description", NS)
        if desc is None:
            desc = ET.Element("description")
            pm.insert(1, desc)
        desc.text = f"<![CDATA[{html}]]>"
        updated += 1
    tree.write(kml_path, encoding="utf-8", xml_declaration=True)
    return updated


def inject_description_table(kml_path: str) -> int:
    """
    Build an HTML description with an allow/deny legend plus the attribute table
    from SimpleData fields so clients that ignore SchemaData still show attributes.
    """
    ET.register_namespace("", KML_NS)
    tree = ET.parse(kml_path)
    root = tree.getroot()
    updated = 0
    for pm in root.findall(".//kml:Placemark", NS):
        ext = pm.find("kml:ExtendedData", NS)
        if ext is None:
            continue

        def flag(val: str) -> str:
            v = (val or "").strip().lower()
            return "🟢" if v and v not in {"no", "closed"} else "🔴"

        def normalize_date(val: str | None) -> str:
            if not val:
                return ""
            v = val.strip()
            return "Open" if v == "01/01-12/31" else v

        def first_nonempty(field_names: list[str]) -> str | None:
            for fname in field_names:
                val = _find_simpledata_value(pm, fname)
                if val:
                    return val
            return None

        # Vehicle permissions with optional date windows.
        access_rows = [
            (
                "Roads open to highway legal vehicles only",
                ["PASSENGERV"],
                ["PASSENGE_1"],
            ),
            (
                "Roads open to all vehicles",
                ["HIGHCLEARA"],
                ["HIGHCLEA_1"],
            ),
            (
                'Trails open to vehicles 50 inches or less in width (ATV, motorcycle, etc.)',
                ["ATV"],
                ["ATV_DATESO"],
            ),
            (
                "Trails open to all (full size) vehicles",
                ["TRUCK"],
                ["TRUCK_DATE"],
            ),
            (
                "Trails open to motorcycles only (single track)",
                ["MOTORCYCLE"],
                ["MOTORCYC_1"],
            ),
            (
                "Trails open to tracked vehicles / snowmobiles",
                ["SNOWMOBILE", "TRACKED_OH", "TRACKED__2"],
                ["SNOW_DATES", "TRACKED__1", "TRACKED__3"],
            ),
        ]

        legend_rows = "".join(
            f"<tr>"
            f"<td>{flag(first_nonempty(allow_fields))}</td>"
            f"<td>{label}</td>"
            f"<td style=\"white-space:nowrap;width:200px;\">{normalize_date(first_nonempty(date_fields))}</td>"
            f"</tr>"
            for (label, allow_fields, date_fields) in access_rows
        )
        legend_table = (
            "<table style=\"width:100%;\">"
            "<tr><th>Status</th><th>Vehicle</th><th style=\"white-space:nowrap;width:200px;\">Dates</th></tr>"
            f"{legend_rows}"
            "</table>"
        )

        # Collect values preserving source order.
        values: list[tuple[str, str]] = []
        for sd in ext.findall(".//kml:SimpleData", NS):
            name = sd.get("name")
            val = (sd.text or "").strip()
            if not name or not val:
                continue
            values.append((name, val))

        if not values:
            continue

        # Priority order for display.
        priority = ["ID", "NAME", "NAME_LONG", "GIS_MILES", "SEASONAL", "FORESTNAME"]
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

        html = (
            "<div>%s</div>"
            "<br/>"
            "<br/>"
            "<div><table>%s</table></div>"
        ) % (legend_table, "".join(rows))
        desc = pm.find("kml:description", NS)
        if desc is None:
            desc = ET.Element("description")
            pm.insert(1, desc)
        desc.text = _CDATA(html)
        updated += 1
    tree.write(kml_path, encoding="utf-8", xml_declaration=True)
    return updated


def inject_generic_description_table(
    kml_path: str,
    priority_fields: list[str] | tuple[str, ...],
    heading: str = "",
) -> int:
    """
    Build a simple HTML description table, ordering a given set of priority fields first.
    Useful for non-motorized layers where the MVUM access legend does not apply.
    """
    priority = list(priority_fields)
    ET.register_namespace("", KML_NS)
    tree = ET.parse(kml_path)
    root = tree.getroot()
    updated = 0

    for pm in root.findall(".//kml:Placemark", NS):
        ext = pm.find("kml:ExtendedData", NS)
        if ext is None:
            continue

        values: list[tuple[str, str]] = []
        for sd in ext.findall(".//kml:SimpleData", NS):
            name = sd.get("name")
            val = (sd.text or "").strip()
            if not name or not val:
                continue
            values.append((name, val))
        if not values:
            continue

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

        prefix = f"<div><b>{heading}</b></div><br/>" if heading else ""
        html = f"{prefix}<div><table>{''.join(rows)}</table></div>"

        desc = pm.find("kml:description", NS)
        if desc is None:
            desc = ET.Element("description")
            pm.insert(1, desc)
        desc.text = _CDATA(html)
        updated += 1

    tree.write(kml_path, encoding="utf-8", xml_declaration=True)
    return updated


def set_kml_linestyle(kml_path: str, line_color: str, line_width: str) -> None:
    """Force LineStyle color/width for all Placemarks in a KML."""
    ET.register_namespace("", KML_NS)
    tree = ET.parse(kml_path)
    root = tree.getroot()

    def ensure_style(pm: ET.Element) -> ET.Element:
        style = pm.find("kml:Style", NS)
        if style is None:
            style = ET.Element("Style")
            pm.insert(0, style)
        return style

    def ensure_linestyle(style: ET.Element) -> ET.Element:
        ls = style.find("kml:LineStyle", NS)
        if ls is None:
            ls = ET.Element("LineStyle")
            style.append(ls)
        return ls

    changed = False
    for pm in root.findall(".//kml:Placemark", NS):
        style = ensure_style(pm)
        ls = ensure_linestyle(style)
        c = ls.find("kml:color", NS)
        if c is None:
            c = ET.Element("color")
            ls.append(c)
        w = ls.find("kml:width", NS)
        if w is None:
            w = ET.Element("width")
            ls.append(w)
        c.text = line_color
        w.text = line_width
        changed = True

    if changed:
        tree.write(kml_path, encoding="utf-8", xml_declaration=True)


def set_kml_polygon_styles(
    kml_path: str,
    field_name: str,
    palette: list[str],
    line_width: str = "2",
    fill_alpha: str | None = None,
) -> None:
    """
    Apply per-feature LineStyle/PolyStyle colors based on a numeric field (e.g., GMUID mod palette).
    palette colors should be KML AABBGGRR strings (e.g., 'ff00ffff').
    """
    if not palette:
        return
    ET.register_namespace("", KML_NS)
    tree = ET.parse(kml_path)
    root = tree.getroot()
    changed = False

    for pm in root.findall(".//kml:Placemark", NS):
        val = _find_simpledata_value(pm, field_name)
        try:
            idx = int(val) % len(palette) if val is not None else 0
        except ValueError:
            idx = 0
        color = palette[idx]

        style = pm.find("kml:Style", NS)
        if style is None:
            style = ET.Element("Style")
            pm.insert(0, style)

        ls = style.find("kml:LineStyle", NS)
        if ls is None:
            ls = ET.Element("LineStyle")
            style.append(ls)
        c = ls.find("kml:color", NS)
        if c is None:
            c = ET.Element("color")
            ls.append(c)
        w = ls.find("kml:width", NS)
        if w is None:
            w = ET.Element("width")
            ls.append(w)
        c.text = color
        w.text = line_width

        ps = style.find("kml:PolyStyle", NS)
        if ps is None:
            ps = ET.Element("PolyStyle")
            style.append(ps)
        pc = ps.find("kml:color", NS)
        if pc is None:
            pc = ET.Element("color")
            ps.append(pc)
        fill = ps.find("kml:fill", NS)
        if fill is None:
            fill = ET.Element("fill")
            ps.append(fill)
        outline = ps.find("kml:outline", NS)
        if outline is None:
            outline = ET.Element("outline")
            ps.append(outline)
        if fill_alpha:
            # fill_alpha should be 2 hex chars (00-ff) representing desired alpha.
            # Apply it to the existing BBGGRR from the palette.
            base = color[2:]  # strip AA from AABBGGRR -> BBGGRR
            pc.text = fill_alpha + base
        else:
            pc.text = color
        fill.text = "1"
        outline.text = "1"
        changed = True

    if changed:
        tree.write(kml_path, encoding="utf-8", xml_declaration=True)


def make_kmz(kml_path: str, kmz_path: str, extra_files: list[str] | None = None) -> None:
    # KMZ is just a zipped KML; optionally bundle extra assets (e.g., icon PNGs).
    extra_files = extra_files or []
    with ZipFile(kmz_path, "w", compression=ZIP_DEFLATED) as zf:
        zf.write(kml_path, arcname=Path(kml_path).name)
        for path_str in extra_files:
            p = Path(path_str)
            if p.exists():
                zf.write(p, arcname=p.name)
            else:
                print(f"WARNING: KMZ extra file not found, skipping: {p}")


def harmonize_document_names(kml_path: str, name: str) -> None:
    """Set Document and top-level Folder <name> to a consistent value."""
    ET.register_namespace("", KML_NS)
    tree = ET.parse(kml_path)
    root = tree.getroot()
    doc = root.find("kml:Document", NS)
    if doc is not None:
        doc_name = doc.find("kml:name", NS)
        if doc_name is None:
            doc_name = ET.SubElement(doc, "name")
        doc_name.text = name
        for folder in doc.findall("kml:Folder", NS):
            fname = folder.find("kml:name", NS)
            if fname is None:
                fname = ET.SubElement(folder, "name")
            fname.text = name
    tree.write(kml_path, encoding="utf-8", xml_declaration=True)


def make_zip_archive(paths: list[str], zip_path: str) -> None:
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as zf:
        for path_str in paths:
            p = Path(path_str)
            if p.exists():
                zf.write(p, arcname=p.name)
            else:
                print(f"WARNING: archive file not found, skipping: {p}")


def extract_parts_for_combination(doc: ET.Element) -> tuple[list[ET.Element], list[ET.Element], list[ET.Element]]:
    """
    Split a Document into schemas, styles, and all other children so we can
    combine multiple layers under one Document with separate folders.
    """
    schemas: list[ET.Element] = []
    styles: list[ET.Element] = []
    others: list[ET.Element] = []
    for child in list(doc):
        if child.tag.endswith("Schema"):
            schemas.append(copy.deepcopy(child))
        elif child.tag.endswith("Style"):
            styles.append(copy.deepcopy(child))
        else:
            others.append(copy.deepcopy(child))
    return schemas, styles, others


def combine_kml_layers(trails_kml: str, roads_kml: str, out_kml: str, doc_name: str) -> None:
    """
    Build a single KML with two folders (Trails, Roads) so ATAK can toggle them.
    Keeps schemas and styles from both sources (style IDs should be distinct).
    """
    ET.register_namespace("", KML_NS)
    ET.register_namespace("gx", GX_NS)

    t_tree = ET.parse(trails_kml)
    r_tree = ET.parse(roads_kml)
    t_doc = t_tree.getroot().find("kml:Document", NS)
    r_doc = r_tree.getroot().find("kml:Document", NS)
    if t_doc is None or r_doc is None:
        raise RuntimeError("Missing Document element when combining KML layers.")

    t_schemas, t_styles, t_others = extract_parts_for_combination(t_doc)
    r_schemas, r_styles, r_others = extract_parts_for_combination(r_doc)

    def k(tag: str) -> str:
        return f"{{{KML_NS}}}{tag}"

    root = ET.Element(k("kml"))
    doc = ET.SubElement(root, k("Document"), {"id": "root_doc"})
    name_el = ET.SubElement(doc, k("name"))
    name_el.text = doc_name

    # Schemas first
    for s in t_schemas + r_schemas:
        doc.append(copy.deepcopy(s))

    # Styles (avoid duplicates by id)
    seen_style_ids = set()
    for s in t_styles + r_styles:
        sid = s.get("id")
        if sid and sid in seen_style_ids:
            continue
        if sid:
            seen_style_ids.add(sid)
        doc.append(copy.deepcopy(s))

    def make_folder(folder_name: str, children: list[ET.Element]) -> ET.Element:
        f = ET.Element(k("Folder"))
        n = ET.SubElement(f, k("name"))
        n.text = folder_name
        for ch in children:
            f.append(copy.deepcopy(ch))
        return f

    doc.append(make_folder("Trails", t_others))
    doc.append(make_folder("Roads", r_others))

    for desc in root.findall(".//kml:description", NS):
        if desc.text:
            desc.text = _CDATA(desc.text)

    ET.ElementTree(root).write(out_kml, encoding="utf-8", xml_declaration=True)
