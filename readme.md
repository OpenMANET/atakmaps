# ATAK Map Projects
-----------------

This repo holds various ATAK-related map projects and may drift over time as different data/maps are used. Each project lives in its own folder under `projects/`.

## Projects
- USFS MVUM — Motor Vehicle Use Map export to ATAK KML/KMZ (roads/trails, labels, access legend). Requires MVUM roads/trails shapefiles placed in `projects/mvum/inputs/`; see `projects/mvum/readme.md`.
- USFS Trails (non-motorized) — Exports the USFS TrailNFS_Publish dataset as per-state KMZs for hiking/bike/snow; motorized segments are filtered out because MVUM covers those. Input shapefile lives in `projects/usfs/inputs/`; see `projects/usfs/readme.md`.
- Colorado CoTrip traffic cameras — built so ATAK users can view Colorado CoTrip camera feeds (https://maps.cotrip.org/list/events) in-app. `projects/colorado-traffic-cameras/cotrip.py` pulls all camera coordinates and HLS URLs from the CoTrip APIs into `co_cotrip_cameras.json`, and `convert_cot.py` turns that into a CoT mission package for ATAK.
- Colorado Hunting GMUs — export Colorado Game Management Units to ATAK KMZ. Download the GMU shapefile from https://geodata.colorado.gov/datasets/2c0794ece2ee4c8d9ac1f64cda8d0216_0/explore into `projects/colorado-hunting/inputs/`, then run `projects/colorado-hunting/main.py`.


## Links
This PDF has been invaluable for information on ATAK KML styling, no one else seems to have covered this information, at this level of detail. This is also included in the `/docs` folder, just to ensure it's not lost.
https://mappingsupport.com/p2/atak/pdf/atak_arcgis_tips.pdf
