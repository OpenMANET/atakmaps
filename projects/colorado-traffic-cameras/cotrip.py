#!/usr/bin/env python3
from __future__ import annotations

import json
import time
import random
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple
from collections import deque


CO_BBOX = dict(west=-109.0603, south=36.9924, east=-102.0415, north=41.0034)

MAP_URL = "https://www.cotrip.org/api/graphql"
VIEWS_URL = "https://maps.cotrip.org/api/graphql"

# IMPORTANT: This is the "working" shape you discovered (Test C style)
MAP_BATCH_QUERY = """
query MapFeatures($input: MapFeaturesArgs!) {
  mapFeaturesQuery(input: $input) {
    mapFeatures {
      __typename
      uri
      title
      bbox
      ... on Camera { active }
      ... on Cluster { maxZoom }
      features { id geometry type }
    }
    error { message type }
  }
}
"""

VIEWS_QUERY = """
query ($input: ListArgs!) {
  listCameraViewsQuery(input: $input) {
    cameraViews {
      category
      sources { type src }
      parentCollection { uri title }
      lastUpdated { timestamp timezone }
    }
    totalRecords
    error { message type }
  }
}
"""

HEADERS_MAP = {
    "content-type": "application/json",
    "origin": "https://www.cotrip.org",
    "referer": "https://www.cotrip.org/travel-information/traveler-information-system-map/",
    "user-agent": "Mozilla/5.0",
}

HEADERS_VIEWS = {
    "content-type": "application/json",
    "origin": "https://maps.cotrip.org",
    "user-agent": "Mozilla/5.0",
}


def post_json_with_retries(
    url: str,
    headers: Dict[str, str],
    payload: Any,
    *,
    max_attempts: int = 8,
    base_sleep: float = 0.6,
    jitter: float = 0.25,
) -> Any:
    """
    POST JSON and retry on transient "Server error." (GraphQL or HTTP).
    payload may be dict or list (batch).
    """
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")

    last_text: Optional[str] = None

    for attempt in range(1, max_attempts + 1):
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.load(resp)

            # Batch responses return a list of result objects.
            # Single responses return dict.
            # Detect transient GraphQL error(s).
            def has_server_error(obj: Any) -> bool:
                if isinstance(obj, dict) and obj.get("errors"):
                    msg = obj["errors"][0].get("message", "")
                    return "Server error" in msg
                return False

            if isinstance(data, list):
                if any(has_server_error(x) for x in data):
                    raise RuntimeError("Server error.")
            elif has_server_error(data):
                raise RuntimeError("Server error.")

            return data

        except urllib.error.HTTPError as e:
            raw = e.read()
            text = raw.decode("utf-8", errors="replace")
            last_text = f"HTTP {e.code}: {text}"

            if "Server error" in text:
                sleep = base_sleep * (2 ** (attempt - 1))
                sleep *= 1.0 + random.uniform(-jitter, jitter)
                time.sleep(min(sleep, 20.0))
                continue

            raise RuntimeError(f"HTTP error from {url}: {last_text}") from None

        except Exception as e:
            last_text = str(e)
            # retry for transient failures
            sleep = base_sleep * (2 ** (attempt - 1))
            sleep *= 1.0 + random.uniform(-jitter, jitter)
            time.sleep(min(sleep, 20.0))
            continue

    raise RuntimeError(f"Exceeded retries for {url}. Last error: {last_text}")


def fetch_all_camera_views_hls(limit: int = 250) -> Dict[str, List[Dict[str, str]]]:
    """
    Returns: { "camera/<id>": [ {"type": "...", "src": "..."}, ... ] }
    Keeps only HLS (application/x-mpegURL).
    """
    hls_by_camera: Dict[str, List[Dict[str, str]]] = {}
    offset = 0
    total: Optional[int] = None

    while True:
        variables = {
            "input": {
                **CO_BBOX,
                "sortDirection": "DESC",
                "sortType": "ROADWAY",
                "freeSearchTerm": "",
                "classificationsOrSlugs": [],
                "recordLimit": limit,
                "recordOffset": offset,
            }
        }

        resp = post_json_with_retries(
            VIEWS_URL, HEADERS_VIEWS, {"query": VIEWS_QUERY, "variables": variables}
        )

        if resp.get("errors"):
            raise RuntimeError(resp["errors"])

        data = resp["data"]["listCameraViewsQuery"]
        if data.get("error"):
            raise RuntimeError(data["error"])

        if total is None:
            total = int(data["totalRecords"])
            print(f"[views] totalRecords={total}")

        rows = data.get("cameraViews") or []
        print(f"[views] offset={offset} got={len(rows)}")

        for v in rows:
            parent = v.get("parentCollection") or {}
            cam_uri = parent.get("uri")
            if not cam_uri:
                continue

            for src in v.get("sources") or []:
                if src.get("type") == "application/x-mpegURL" and src.get("src"):
                    hls_by_camera.setdefault(cam_uri, [])
                    if not any(x["src"] == src["src"] for x in hls_by_camera[cam_uri]):
                        hls_by_camera[cam_uri].append({"type": src["type"], "src": src["src"]})

        if not rows or (total is not None and offset + limit >= total):
            break

        offset += limit
        time.sleep(0.1)

    print(f"[views] cameras with HLS={len(hls_by_camera)}")
    return hls_by_camera


def extract_lon_lat_from_features(features: List[Dict[str, Any]]) -> Tuple[Optional[float], Optional[float]]:
    # features are GeoJSON features with geometry = {type, coordinates}
    for f in features or []:
        geom = f.get("geometry") or {}
        if geom.get("type") == "Point":
            coords = geom.get("coordinates") or []
            if isinstance(coords, list) and len(coords) >= 2:
                return coords[0], coords[1]
    return None, None


def fetch_mapfeatures_batch(bbox: Dict[str, float], zoom: int) -> List[Dict[str, Any]]:
    payload = [
        {
            "query": " ".join(MAP_BATCH_QUERY.split()),
            "variables": {
                "input": {
                    "north": bbox["north"],
                    "south": bbox["south"],
                    "east": bbox["east"],
                    "west": bbox["west"],
                    "zoom": zoom,
                    "layerSlugs": ["normalCameras"],
                    "nonClusterableUris": ["travel-information/traveler-information-system-map"],
                }
            },
        }
    ]

    resp_list = post_json_with_retries(MAP_URL, HEADERS_MAP, payload)
    if not isinstance(resp_list, list) or not resp_list:
        raise RuntimeError(f"Unexpected batch response: {type(resp_list)}")

    resp = resp_list[0]
    if resp.get("errors"):
        raise RuntimeError(resp["errors"])

    data = resp["data"]["mapFeaturesQuery"]
    if data.get("error"):
        raise RuntimeError(data["error"])

    return data.get("mapFeatures") or []


def fetch_all_cameras_with_coords(
    start_zoom: int = 7,
    max_zoom: int = 16,
) -> Dict[str, Dict[str, Any]]:
    """
    Cluster-expands starting at low zoom. Uses cluster bbox to zoom in.
    Returns dict keyed by camera uri.
    """
    cameras: Dict[str, Dict[str, Any]] = {}

    q = deque()
    q.append((dict(north=CO_BBOX["north"], south=CO_BBOX["south"], east=CO_BBOX["east"], west=CO_BBOX["west"]), start_zoom))

    seen_cluster_jobs = set()

    while q:
        bbox, zoom = q.popleft()
        job_key = (round(bbox["west"], 6), round(bbox["south"], 6), round(bbox["east"], 6), round(bbox["north"], 6), zoom)
        if job_key in seen_cluster_jobs:
            continue
        seen_cluster_jobs.add(job_key)

        feats = fetch_mapfeatures_batch(bbox, zoom)

        cluster_count = 0
        cam_count = 0

        for item in feats:
            t = item.get("__typename")
            if t == "Camera":
                cam_count += 1
                uri = item.get("uri")
                if not uri:
                    continue
                lon, lat = extract_lon_lat_from_features(item.get("features") or [])
                cameras[uri] = {
                    "uri": uri,
                    "title": item.get("title"),
                    "active": item.get("active"),
                    "lon": lon,
                    "lat": lat,
                }
            elif t == "Cluster":
                cluster_count += 1
                cb = item.get("bbox")
                if not (isinstance(cb, list) and len(cb) == 4):
                    continue
                next_zoom = zoom + 1
                mz = item.get("maxZoom")
                if isinstance(mz, int) and mz > next_zoom:
                    next_zoom = mz
                next_zoom = min(next_zoom, max_zoom)
                if next_zoom <= zoom:
                    continue
                q.append((dict(west=cb[0], south=cb[1], east=cb[2], north=cb[3]), next_zoom))

        print(f"[map] zoom={zoom} cams={cam_count} clusters={cluster_count} queue={len(q)} total_cams={len(cameras)}")
        time.sleep(0.05)

    return cameras


def main() -> None:
    hls_by_camera = fetch_all_camera_views_hls(limit=250)
    cams = fetch_all_cameras_with_coords(start_zoom=7, max_zoom=16)

    merged = []
    for uri, cam in cams.items():
        merged.append({**cam, "hls_sources": hls_by_camera.get(uri, [])})

    def uri_key(x: Dict[str, Any]) -> Tuple[int, str]:
        u = x.get("uri", "")
        try:
            return (int(u.split("/")[1]), u)
        except Exception:
            return (10**18, u)

    merged.sort(key=uri_key)

    out_path = "co_cotrip_cameras.json"
    with open(out_path, "w") as f:
        json.dump(
            {
                "generated_at_unix_ms": int(time.time() * 1000),
                "bbox": CO_BBOX,
                "count": len(merged),
                "cameras": merged,
            },
            f,
            indent=2,
        )

    print(f"Wrote {out_path} ({len(merged)} cameras)")
    print(f"With HLS sources: {sum(1 for c in merged if c['hls_sources'])}")


if __name__ == "__main__":
    main()
