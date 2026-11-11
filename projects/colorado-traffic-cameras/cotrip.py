#!/usr/bin/env python3
"""Refresh the Colorado CoTrip camera inventory from the current 511 API."""

from __future__ import annotations

import argparse
import json
import random
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT = PROJECT_DIR / "co_cotrip_cameras.json"
CAMERAS_URL = "https://api-511x-co.carsprogram.org/cameras/map-features"
CO_BBOX = {"west": -109.0603, "south": 36.9924, "east": -102.0415, "north": 41.0034}


def fetch_json(
    url: str,
    *,
    max_attempts: int = 5,
    timeout: int = 60,
) -> dict[str, Any]:
    """Fetch JSON with bounded retries for transient service failures."""
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "OpenMANET-atakmaps/1.0",
        },
    )
    last_error: Exception | None = None

    for attempt in range(max_attempts):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.load(response)
            if not isinstance(payload, dict):
                raise RuntimeError(f"Unexpected response type: {type(payload).__name__}")
            return payload
        except urllib.error.HTTPError as exc:
            last_error = exc
            exc.close()
            if exc.code < 500 and exc.code != 429:
                raise
        except (OSError, urllib.error.URLError, json.JSONDecodeError, RuntimeError) as exc:
            last_error = exc

        if attempt < max_attempts - 1:
            delay = min(2**attempt, 15) * random.uniform(0.8, 1.2)
            time.sleep(delay)

    raise RuntimeError(f"Unable to refresh CoTrip cameras: {last_error}")


def camera_from_feature(feature: dict[str, Any]) -> dict[str, Any] | None:
    """Convert one 511 GeoJSON feature to the repository's stable schema."""
    properties = feature.get("properties") or {}
    geometry = feature.get("geometry") or {}
    coordinates = geometry.get("coordinates") or []
    camera_id = properties.get("id")

    if (
        camera_id in (None, "")
        or geometry.get("type") != "Point"
        or not isinstance(coordinates, list)
        or len(coordinates) < 2
        or properties.get("public") is False
    ):
        return None

    hls_sources: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for view in properties.get("views") or []:
        url = str(view.get("url") or "").strip()
        if view.get("type") != "WMP" or view.get("broken") is True or not url:
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        hls_sources.append(
            {
                "type": "application/x-mpegURL",
                "src": url,
                "name": str(view.get("name") or properties.get("name") or camera_id),
            }
        )

    return {
        "uri": f"camera/{camera_id}",
        "title": properties.get("name") or properties.get("tooltip") or f"Camera {camera_id}",
        "active": bool(hls_sources),
        "lon": coordinates[0],
        "lat": coordinates[1],
        "hls_sources": hls_sources,
    }


def build_inventory(payload: dict[str, Any]) -> list[dict[str, Any]]:
    cameras = []
    for feature in payload.get("features") or []:
        camera = camera_from_feature(feature)
        if camera:
            cameras.append(camera)

    def sort_key(camera: dict[str, Any]) -> tuple[int, str]:
        uri = str(camera.get("uri") or "")
        try:
            return int(uri.rsplit("/", 1)[-1]), uri
        except ValueError:
            return 10**18, uri

    cameras.sort(key=sort_key)
    return cameras


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=CAMERAS_URL, help="CoTrip camera GeoJSON URL")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = fetch_json(args.source)
    cameras = build_inventory(payload)
    hls_count = sum(bool(camera["hls_sources"]) for camera in cameras)
    view_count = sum(len(camera["hls_sources"]) for camera in cameras)

    output = {
        "generated_at_unix_ms": int(time.time() * 1000),
        "source": args.source,
        "bbox": CO_BBOX,
        "count": len(cameras),
        "hls_camera_count": hls_count,
        "hls_view_count": view_count,
        "cameras": cameras,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {args.output} ({len(cameras)} cameras)")
    print(f"Cameras with working HLS views: {hls_count} ({view_count} views)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
