USFS Trails (Non‑Motorized) Export
==================================

This tool exports the USFS TrailNFS_Publish layer to per‑state, non‑motorized ATAK KMZ files. It filters out motorized segments (already covered by the MVUM exporter) so you can load hiking/bike/snow‑focused trails alongside the MVUM motorized maps.

Connection to MVUM
- MVUM remains the authoritative source for motorized travel; use the MVUM exporter in `projects/mvum` for roads/trails with legal motorized access.
- This exporter pulls the broader USFS TrailNFS_Publish dataset and **excludes motorized** features (`TERRA_MOTO='Y'` or `MVUM_SYMBO` set) to avoid overlap. You can load both layers in ATAK and toggle as needed.

Inputs
- `projects/usfs/inputs/National_Forest_System_Trails_(Feature_Layer).shp` (TrailNFS_Publish shapefile).
- Source link: https://data-usfs.hub.arcgis.com/datasets/usfs::national-forest-system-trails-feature-layer — download the non-motorized TrailNFS_Publish shapefile and extract it into `projects/usfs/inputs/`.

Outputs
- Per-state KMZ files in `projects/usfs/outputs/USFS_trails_{STATE}.kmz`.
- By default, only Colorado is exported; adjust `RUN_ALL_STATES` or `DEFAULT_STATES` in `projects/usfs/main.py` to include more states (bboxes come from `state_bboxes.py`).
- Styling/labels: bright cyan lines for non-motorized trails, with embedded label points using `TRAIL_NAME`/`TRAIL_NO`, and a concise description table (class, surface, width/grade, allowed uses).

How to run
1) Ensure GDAL/OGR with Python bindings is installed (e.g., `brew install gdal` on macOS).
2) Download/import the TrailNFS_Publish shapefile into `projects/usfs/inputs/` (already present in this repo).
3) Run the exporter:
   - Default (Colorado only): `python3 projects/usfs/main.py`
   - All states: set `RUN_ALL_STATES = True` in `main.py`.
4) Copy the KMZ(s) from `projects/usfs/outputs/` to your ATAK device. Import one at a time for better performance.

Prebuilt maps (no build needed)
- Latest release: <https://github.com/OpenMANET/atakmaps/releases>
- Download `USFS_trails.zip` for ready-to-import per-state non-motorized trail KMZs.

What’s in the KMZ
- Trails filtered to non‑motorized (motorized segments removed).
- Labels from `TRAIL_NAME`/`TRAIL_NO`.
- Description table with trail class, surface/firmness, grade/width, and allowed uses for quick field reference.
