#!/usr/bin/env python3
"""
Generate a CoT mission package for CoTrip cameras with HLS feeds.
Output: co_cotrip_cameras_mp.zip under outputs/.
"""

from __future__ import annotations

import json
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

INPUT_JSON = Path(__file__).resolve().parent / "co_cotrip_cameras.json"
OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"
OUTPUT_ZIP = OUTPUT_DIR / "co_cotrip_cameras_mp.zip"


def isoformat(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_video_url(url: str) -> tuple[str, int, str, str]:
    parsed = urlparse(url)
    protocol = parsed.scheme or "https"
    address = parsed.hostname or parsed.netloc or ""
    port = parsed.port or (443 if protocol == "https" else 80)
    path = parsed.path or ""
    if parsed.query:
        path = f"{path}?{parsed.query}"
    return address, port, protocol, path


def make_cot_event(uid: str, callsign: str, lon: float, lat: float, url: str, time_now: datetime, stale_time: datetime) -> ET.Element:
    video_uid = str(uuid.uuid4())
    address, port, protocol, path = parse_video_url(url)
    event = ET.Element(
        "event",
        {
            "version": "2.0",
            "uid": uid,
            "type": "b-m-p-s-p-loc",
            "how": "h-g-i-g-o",
            "access": "Undefined",
            "time": isoformat(time_now),
            "start": isoformat(time_now),
            "stale": isoformat(stale_time),
        },
    )
    ET.SubElement(
        event,
        "point",
        lat=str(lat),
        lon=str(lon),
        hae="0",
        ce="9999999.0",
        le="9999999.0",
    )
    detail = ET.SubElement(event, "detail")
    ET.SubElement(detail, "status", readiness="true")
    ET.SubElement(detail, "archive")
    sensor = ET.SubElement(
        detail,
        "sensor",
        elevation="0",
        vfov="45",
        fovBlue="1.0",
        fovRed="1.0",
        strokeWeight="0.7",
        roll="0",
        range="36",
        azimuth="0",
        rangeLineStrokeWeight="1.0",
        fov="45",
        hideFov="true",
        rangeLineStrokeColor="-3355444",
        fovGreen="1.0",
        displayMagneticReference="0",
        strokeColor="-3355444",
        rangeLines="100",
        fovAlpha="0.2980392156862745",
    )
    video = ET.SubElement(detail, "__video", uid=video_uid, url=url)
    ET.SubElement(
        video,
        "ConnectionEntry",
        networkTimeout="12000",
        uid=video_uid,
        path=path,
        protocol=protocol,
        bufferTime="-1",
        address=address,
        port=str(port),
        roverPort="-1",
        rtspReliable="0",
        ignoreEmbeddedKLV="false",
        alias=callsign,
    )
    ET.SubElement(detail, "archive")
    ET.SubElement(detail, "link", uid=uid, relation="p-p")
    ET.SubElement(detail, "remarks")
    ET.SubElement(detail, "color", argb="-1")
    ET.SubElement(detail, "contact", callsign=callsign)
    ET.SubElement(detail, "precisionlocation", altsrc="DTED2")
    return event


def build_manifest(uids: list[str]) -> ET.ElementTree:
    root = ET.Element("MissionPackageManifest", version="2")
    config = ET.SubElement(root, "Configuration")
    ET.SubElement(config, "Parameter", name="uid", value=str(uuid.uuid4()))
    ET.SubElement(config, "Parameter", name="name", value="co_cotrip_cameras")
    contents = ET.SubElement(root, "Contents")
    for uid in uids:
        cont = ET.SubElement(contents, "Content", ignore="false", zipEntry=f"{uid}.cot")
        ET.SubElement(cont, "Parameter", name="uid", value=uid)
    return ET.ElementTree(root)


def main() -> int:
    if not INPUT_JSON.exists():
        print(f"Missing input: {INPUT_JSON}")
        return 2
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    data = json.loads(INPUT_JSON.read_text())
    cams = data.get("cameras") or []

    cot_files = []
    manifest_uids = []
    now = datetime.now(timezone.utc)
    stale = now + timedelta(days=365)

    for cam in cams:
        hls = cam.get("hls_sources") or []
        urls = [src.get("src") for src in hls if src.get("src")]
        if not urls:
            continue
        lon, lat = cam.get("lon"), cam.get("lat")
        if lon is None or lat is None:
            continue
        uid = cam.get("uri") or f"cotrip-{uuid.uuid4()}"
        callsign = cam.get("title") or uid
        event = make_cot_event(uid, callsign, lon, lat, urls[0], now, stale)
        safe_uid = uid.replace("/", "_")
        cot_path = OUTPUT_DIR / f"{safe_uid}.cot"
        ET.ElementTree(event).write(cot_path, encoding="utf-8", xml_declaration=True)
        cot_files.append(cot_path)
        manifest_uids.append(safe_uid)

    manifest = build_manifest(manifest_uids)
    manifest_path = OUTPUT_DIR / "manifest.xml"
    manifest.write(manifest_path, encoding="utf-8", xml_declaration=True)

    with zipfile.ZipFile(OUTPUT_ZIP, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(manifest_path, arcname="MANIFEST/manifest.xml")
        for cot_path in cot_files:
            zf.write(cot_path, arcname=cot_path.name)

    print(f"Wrote mission package: {OUTPUT_ZIP} (events: {len(cot_files)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
