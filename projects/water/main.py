#!/usr/bin/env python3
"""Build ATAK-friendly USGS hydrography and EPA water-quality KMZs."""

from __future__ import annotations

import argparse
import html
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT))

from state_bboxes import STATE_BBOXES  # noqa: E402

KML_NS = "http://www.opengis.net/kml/2.2"
ET.register_namespace("", KML_NS)

USGS_BASE = (
    "https://3dhp.nationalmap.gov/arcgis/rest/services/"
    "usgs_3dhp_all/FeatureServer"
)
EPA_BASE = (
    "https://services.arcgis.com/cJ9YHowT8TU7DUyn/ArcGIS/rest/services/"
    "ATTAINS_Assessment/FeatureServer"
)

# KML colors use AABBGGRR.
STYLES = {
    "flowline": {"line": "ffff8c00", "width": "2"},
    "waterbody": {"line": "ffff8c00", "width": "2", "poly": "55ff8c00"},
    "spring": {"line": "ff00ffff", "width": "2", "icon": "ff00ffff"},
    "quality-good": {"line": "ff00aa00", "width": "4", "poly": "4400aa00"},
    "quality-threatened": {"line": "ff00a5ff", "width": "4", "poly": "4400a5ff"},
    "quality-impaired": {"line": "ff0000ff", "width": "4", "poly": "440000ff"},
    "quality-unknown": {"line": "ff999999", "width": "3", "poly": "33999999"},
}

POLLUTANT_FIELDS = {
    "algal_growth": "Algal growth",
    "ammonia": "Ammonia",
    "biotoxins": "Biotoxins",
    "chlorine": "Chlorine",
    "dioxins": "Dioxins",
    "fish_consumption_advisory": "Fish consumption advisory",
    "mercury": "Mercury",
    "metals_other_than_mercury": "Metals other than mercury",
    "nutrients": "Nutrients",
    "oil_and_grease": "Oil and grease",
    "oxygen_depletion": "Oxygen depletion",
    "pathogens": "Pathogens",
    "pesticides": "Pesticides",
    "pfas": "PFAS",
    "ph_acidity_caustic_conditions": "pH / acidity / caustic conditions",
    "polychlorinated_biphenyls_pcbs": "PCBs",
    "radiation": "Radiation",
    "sediment": "Sediment",
    "temperature": "Temperature",
    "total_toxics": "Total toxics",
    "toxic_inorganics": "Toxic inorganics",
    "toxic_organics": "Toxic organics",
    "trash": "Trash",
    "turbidity": "Turbidity",
}


def _tag(name: str) -> str:
    return f"{{{KML_NS}}}{name}"


def _request_json(url: str, params: dict[str, Any], retries: int = 4) -> dict[str, Any]:
    encoded = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"{url}?{encoded}",
        headers={"User-Agent": "OpenMANET-atakmaps/1.0"},
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                payload = json.load(response)
            if "error" in payload:
                raise RuntimeError(f"ArcGIS error: {payload['error']}")
            return payload
        except (OSError, urllib.error.URLError, json.JSONDecodeError, RuntimeError):
            if attempt == retries - 1:
                raise
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def fetch_arcgis_features(
    base_url: str,
    layer: int,
    where: str,
    out_fields: Iterable[str],
    *,
    bbox: tuple[float, float, float, float] | None = None,
    page_size: int = 2000,
) -> Iterator[dict[str, Any]]:
    """Yield an ArcGIS FeatureServer query as paged GeoJSON features."""
    offset = 0
    minimum_page_size = min(100, page_size)
    while True:
        params: dict[str, Any] = {
            "where": where,
            "outFields": ",".join(out_fields),
            "returnGeometry": "true",
            "returnZ": "false",
            "outSR": 4326,
            "geometryPrecision": 5,
            # About 5 m at the equator: preserves useful detail while keeping
            # statewide KMLs within a range ATAK can reasonably handle.
            "maxAllowableOffset": 0.00005,
            "orderByFields": "OBJECTID",
            "resultOffset": offset,
            "resultRecordCount": page_size,
            "f": "geojson",
        }
        if bbox:
            params.update(
                {
                    "geometry": ",".join(str(value) for value in bbox),
                    "geometryType": "esriGeometryEnvelope",
                    "inSR": 4326,
                    "spatialRel": "esriSpatialRelIntersects",
                }
            )

        try:
            payload = _request_json(f"{base_url}/{layer}/query", params)
        except urllib.error.HTTPError as exc:
            # Some statewide pages contain unusually complex polygons and the
            # service returns HTTP 500 for the combined response. Resume from
            # the same offset with a smaller page instead of restarting the
            # entire state job.
            if exc.code < 500 or page_size <= minimum_page_size:
                raise
            page_size = max(minimum_page_size, page_size // 2)
            print(
                f"  layer {layer}: retrying offset {offset:,} "
                f"with page size {page_size:,}",
                flush=True,
            )
            continue
        features = payload.get("features", [])
        if not isinstance(features, list):
            raise RuntimeError(f"Unexpected response for layer {layer}: no feature list")
        yield from features
        print(f"  layer {layer}: downloaded {offset + len(features):,} features", flush=True)
        exceeded = bool(
            payload.get("exceededTransferLimit")
            or (payload.get("properties") or {}).get("exceededTransferLimit")
        )
        if not features or (len(features) < page_size and not exceeded):
            break
        offset += len(features)


def _format_date(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        stamp = float(value) / 1000
        return datetime.fromtimestamp(stamp, tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError, OSError):
        return str(value)


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"y", "yes", "true", "1", "t"}


def _table(rows: Iterable[tuple[str, Any]]) -> str:
    rendered = []
    for label, value in rows:
        if value in (None, ""):
            continue
        rendered.append(
            "<tr><td><b>%s</b></td><td>%s</td></tr>"
            % (html.escape(label), html.escape(str(value)))
        )
    return "<table>%s</table>" % "".join(rendered)


def hydro_description(props: dict[str, Any], heading: str) -> str:
    return (
        f"<div><b>{html.escape(heading)}</b></div><br/>"
        + _table(
            [
                ("Name", props.get("gnisidlabel")),
                ("Feature type", props.get("featuretypelabel")),
                ("Length (km)", props.get("lengthkm")),
                ("Area (sq km)", props.get("areasqkm")),
                ("Stream order", props.get("streamorder")),
                ("Flow direction", props.get("flowdirectionlabel")),
                ("Feature date", _format_date(props.get("featuredate"))),
                ("3DHP ID", props.get("id3dhp")),
            ]
        )
    )


def quality_style(props: dict[str, Any]) -> str:
    if _truthy(props.get("isimpaired")) or _truthy(props.get("on303dlist")):
        return "quality-impaired"
    if _truthy(props.get("isthreatened")):
        return "quality-threatened"
    if _truthy(props.get("isassessed")):
        return "quality-good"
    return "quality-unknown"


def quality_description(props: dict[str, Any]) -> str:
    style = quality_style(props)
    label = {
        "quality-impaired": "Impaired / listed",
        "quality-threatened": "Threatened",
        "quality-good": "Assessed; not flagged impaired",
        "quality-unknown": "Assessment status unavailable",
    }[style]
    pollutants = [
        display for field, display in POLLUTANT_FIELDS.items() if _truthy(props.get(field))
    ]
    report = props.get("waterbodyreportlink")
    report_html = ""
    if report:
        safe = html.escape(str(report), quote=True)
        report_html = f'<br/><div><a href="{safe}">EPA waterbody report</a></div>'
    return (
        f"<div><b>EPA ATTAINS Water Quality</b></div>"
        f"<div><b>Status: {html.escape(label)}</b></div><br/>"
        + _table(
            [
                ("Waterbody", props.get("assessmentunitname")),
                ("Assessment unit", props.get("assessmentunitidentifier")),
                ("Overall status", props.get("overallstatus")),
                ("IR category", props.get("ircategory")),
                ("Reporting cycle", props.get("reportingcycle")),
                ("Organization", props.get("organizationname")),
                ("Potential concerns", ", ".join(pollutants)),
                ("Has TMDL", props.get("hastmdl")),
                ("Drinking-water use", props.get("drinkingwater_use")),
                ("Recreation use", props.get("recreation_use")),
                ("Fish-consumption use", props.get("fishconsumption_use")),
            ]
        )
        + report_html
        + "<br/><div><i>Assessment status is not a real-time safety or potability test. "
        "Unassessed or unlisted water may still contain hazards.</i></div>"
    )


def _coordinates(parent: ET.Element, coords: Iterable[Iterable[float]]) -> None:
    el = ET.SubElement(parent, _tag("coordinates"))
    el.text = " ".join(
        f"{point[0]},{point[1]}" + (f",{point[2]}" if len(point) > 2 else ",0")
        for point in coords
    )


def _line(parent: ET.Element, coords: list[list[float]]) -> None:
    line = ET.SubElement(parent, _tag("LineString"))
    ET.SubElement(line, _tag("tessellate")).text = "1"
    ET.SubElement(line, _tag("altitudeMode")).text = "clampToGround"
    _coordinates(line, coords)


def _polygon(parent: ET.Element, rings: list[list[list[float]]]) -> None:
    polygon = ET.SubElement(parent, _tag("Polygon"))
    ET.SubElement(polygon, _tag("tessellate")).text = "1"
    for index, ring in enumerate(rings):
        boundary = ET.SubElement(
            polygon, _tag("outerBoundaryIs" if index == 0 else "innerBoundaryIs")
        )
        linear = ET.SubElement(boundary, _tag("LinearRing"))
        _coordinates(linear, ring)


def append_geometry(parent: ET.Element, geometry: dict[str, Any]) -> None:
    kind = geometry.get("type")
    coords = geometry.get("coordinates")
    if kind == "Point":
        point = ET.SubElement(parent, _tag("Point"))
        _coordinates(point, [coords])
    elif kind == "MultiPoint":
        multi = ET.SubElement(parent, _tag("MultiGeometry"))
        for item in coords:
            append_geometry(multi, {"type": "Point", "coordinates": item})
    elif kind == "LineString":
        _line(parent, coords)
    elif kind == "MultiLineString":
        multi = ET.SubElement(parent, _tag("MultiGeometry"))
        for item in coords:
            _line(multi, item)
    elif kind == "Polygon":
        _polygon(parent, coords)
    elif kind == "MultiPolygon":
        multi = ET.SubElement(parent, _tag("MultiGeometry"))
        for item in coords:
            _polygon(multi, item)
    else:
        raise ValueError(f"Unsupported GeoJSON geometry: {kind}")


def _add_styles(document: ET.Element) -> None:
    for style_id, values in STYLES.items():
        style = ET.SubElement(document, _tag("Style"), {"id": style_id})
        line = ET.SubElement(style, _tag("LineStyle"))
        ET.SubElement(line, _tag("color")).text = values["line"]
        ET.SubElement(line, _tag("width")).text = values["width"]
        if "poly" in values:
            poly = ET.SubElement(style, _tag("PolyStyle"))
            ET.SubElement(poly, _tag("color")).text = values["poly"]
            ET.SubElement(poly, _tag("fill")).text = "1"
            ET.SubElement(poly, _tag("outline")).text = "1"
        if "icon" in values:
            icon = ET.SubElement(style, _tag("IconStyle"))
            ET.SubElement(icon, _tag("color")).text = values["icon"]
            ET.SubElement(icon, _tag("scale")).text = "0.8"
            image = ET.SubElement(icon, _tag("Icon"))
            ET.SubElement(image, _tag("href")).text = (
                "https://maps.google.com/mapfiles/kml/shapes/water.png"
            )


def new_document(name: str) -> tuple[ET.Element, ET.Element]:
    root = ET.Element(_tag("kml"))
    document = ET.SubElement(root, _tag("Document"))
    ET.SubElement(document, _tag("name")).text = name
    ET.SubElement(document, _tag("open")).text = "0"
    _add_styles(document)
    return root, document


def add_folder(
    document: ET.Element,
    name: str,
    features: Iterable[dict[str, Any]],
    *,
    default_style: str,
    description_builder: Any,
    name_fields: tuple[str, ...],
    dynamic_style: bool = False,
) -> int:
    folder = ET.SubElement(document, _tag("Folder"))
    ET.SubElement(folder, _tag("name")).text = name
    ET.SubElement(folder, _tag("visibility")).text = "1"
    count = 0
    for feature in features:
        geometry = feature.get("geometry")
        if not geometry:
            continue
        props = feature.get("properties") or {}
        placemark = ET.SubElement(folder, _tag("Placemark"))
        label = next((props.get(field) for field in name_fields if props.get(field)), None)
        ET.SubElement(placemark, _tag("name")).text = str(label or "Unnamed water feature")
        style_id = quality_style(props) if dynamic_style else default_style
        ET.SubElement(placemark, _tag("styleUrl")).text = f"#{style_id}"
        description = ET.SubElement(placemark, _tag("description"))
        description.text = description_builder(props)
        extended = ET.SubElement(placemark, _tag("ExtendedData"))
        for field, value in props.items():
            if value in (None, ""):
                continue
            # ATTAINS returns dozens of false concern flags per feature. They
            # add substantial bulk without useful information; retain only
            # the flags that are actually set.
            if field in POLLUTANT_FIELDS and not _truthy(value):
                continue
            data = ET.SubElement(extended, _tag("Data"), {"name": str(field)})
            ET.SubElement(data, _tag("value")).text = str(value)
        append_geometry(placemark, geometry)
        count += 1
    if count == 0:
        document.remove(folder)
    return count


def write_kmz(root: ET.Element, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    kml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    with ZipFile(path, "w", ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr("doc.kml", kml)


def _dedupe(features: Iterable[dict[str, Any]], field: str) -> Iterator[dict[str, Any]]:
    seen: set[Any] = set()
    for feature in features:
        value = (feature.get("properties") or {}).get(field)
        key = value if value is not None else json.dumps(feature.get("geometry"), sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        yield feature


def state_query_bboxes(state: str) -> list[tuple[float, float, float, float]]:
    """Return query envelopes, splitting Alaska at the antimeridian."""
    state = state.upper()
    if state == "AK":
        # A single -179..+179 envelope would cover almost the entire northern
        # hemisphere. Separate southeast Alaska from the mainland as well, so
        # the rectangular query does not include most of western Canada.
        return [
            (-180.0, 51.0, -141.0, 72.0),
            (-141.0, 54.0, -129.0, 61.0),
            (172.0, 51.0, 180.0, 54.8),
        ]
    bbox = STATE_BBOXES.get(state)
    return [bbox] if bbox else []


def waterbody_queries(state: str) -> tuple[str, ...]:
    """Return useful waterbody filters at a practical statewide scale."""
    if state.upper() == "AK":
        # Alaska has hundreds of thousands of tiny mapped polygons. Preserve
        # all named waterbodies, but use a larger threshold for unnamed ones so
        # ArcGIS can complete the request and ATAK can load the resulting KMZ.
        return ("gnisidlabel IS NOT NULL", "areasqkm >= 0.25")
    return ("gnisidlabel IS NOT NULL", "areasqkm >= 0.02")


def build_usgs(
    state: str,
    bboxes: list[tuple[float, float, float, float]],
    output_dir: Path,
    page_size: int,
) -> Path:
    print(f"Downloading USGS 3DHP hydrography for {state}...")
    common = ["OBJECTID", "id3dhp", "gnisidlabel", "featuredate", "featuretypelabel"]
    flows = _dedupe(
        (
            feature
            for bbox in bboxes
            for feature in fetch_arcgis_features(
                USGS_BASE,
                50,
                "gnisidlabel IS NOT NULL AND lengthkm >= 0.5",
                [*common, "lengthkm", "flowdirectionlabel", "streamorder"],
                bbox=bbox,
                page_size=page_size,
            )
        ),
        "id3dhp",
    )
    waterbodies = _dedupe(
        (
            feature
            for bbox in bboxes
            for where in waterbody_queries(state)
            for feature in fetch_arcgis_features(
                USGS_BASE,
                60,
                where,
                [*common, "areasqkm"],
                bbox=bbox,
                page_size=page_size,
            )
        ),
        "id3dhp",
    )
    springs = _dedupe(
        (
            feature
            for bbox in bboxes
            for feature in fetch_arcgis_features(
                USGS_BASE,
                20,
                "featuretype = 7",
                common,
                bbox=bbox,
                page_size=page_size,
            )
        ),
        "id3dhp",
    )

    root, document = new_document(f"USGS 3DHP Surface Water - {state}")
    counts = {
        "flowlines": add_folder(
            document,
            "Named streams and flowlines",
            flows,
            default_style="flowline",
            description_builder=lambda props: hydro_description(props, "USGS 3DHP Flowline"),
            name_fields=("gnisidlabel", "featuretypelabel"),
        ),
        "waterbodies": add_folder(
            document,
            "Lakes, ponds, reservoirs, and waterbodies",
            waterbodies,
            default_style="waterbody",
            description_builder=lambda props: hydro_description(props, "USGS 3DHP Waterbody"),
            name_fields=("gnisidlabel", "featuretypelabel"),
        ),
        "springs": add_folder(
            document,
            "Springs",
            springs,
            default_style="spring",
            description_builder=lambda props: hydro_description(props, "USGS 3DHP Spring"),
            name_fields=("gnisidlabel", "featuretypelabel"),
        ),
    }
    path = output_dir / f"USGS_3DHP_{state}.kmz"
    write_kmz(root, path)
    print(f"Created {path} ({counts})")
    return path


def build_epa(state: str, output_dir: Path, page_size: int) -> Path:
    print(f"Downloading EPA ATTAINS assessments for {state}...")
    fields = [
        "OBJECTID",
        "state",
        "organizationname",
        "reportingcycle",
        "assessmentunitidentifier",
        "assessmentunitname",
        "waterbodyreportlink",
        "ircategory",
        "overallstatus",
        "isassessed",
        "isimpaired",
        "isthreatened",
        "on303dlist",
        "hastmdl",
        "drinkingwater_use",
        "recreation_use",
        "fishconsumption_use",
        *POLLUTANT_FIELDS,
    ]
    root, document = new_document(f"EPA ATTAINS Water Quality - {state}")
    counts: dict[str, int] = {}
    for layer, label in ((0, "Assessment points"), (1, "Assessment lines"), (2, "Assessment areas")):
        features = fetch_arcgis_features(
            EPA_BASE,
            layer,
            f"state = '{state}'",
            fields,
            page_size=page_size,
        )
        counts[label] = add_folder(
            document,
            label,
            features,
            default_style="quality-unknown",
            description_builder=quality_description,
            name_fields=("assessmentunitname", "assessmentunitidentifier"),
            dynamic_style=True,
        )
    path = output_dir / f"EPA_ATTAINS_{state}.kmz"
    write_kmz(root, path)
    print(f"Created {path} ({counts})")
    return path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", default="CO", help="two-letter state code (default: CO)")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "outputs",
    )
    parser.add_argument("--page-size", type=int, default=2000)
    parser.add_argument("--skip-usgs", action="store_true")
    parser.add_argument("--skip-epa", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    state = args.state.upper()
    bboxes = state_query_bboxes(state)
    if not bboxes:
        print(f"ERROR: unknown state code {state!r}", file=sys.stderr)
        return 2
    if args.page_size < 1 or args.page_size > 2000:
        print("ERROR: --page-size must be between 1 and 2000", file=sys.stderr)
        return 2
    if args.skip_usgs and args.skip_epa:
        print("ERROR: both sources were skipped", file=sys.stderr)
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    if not args.skip_usgs:
        build_usgs(state, bboxes, args.output_dir, args.page_size)
    if not args.skip_epa:
        build_epa(state, args.output_dir, args.page_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
