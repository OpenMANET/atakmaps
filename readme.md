# ATAK Map Projects
-----------------

This repo holds various ATAK-related map projects and may drift over time as different data/maps are used. Each project lives in its own folder under `projects/`.

## Projects
- USFS MVUM — exports Motor Vehicle Use Map data to ATAK-ready KML/KMZ with access legends; see `projects/mvum/readme.md`.
- USFS Trails (non-motorized) — per-state KMZs for hiking/bike/snow trails from TrailNFS_Publish, with motorized segments removed; see `projects/usfs/readme.md`.
- Colorado CoTrip traffic cameras — CoTrip camera feeds packaged for ATAK data packages; see `projects/colorado-traffic-cameras/README.md`.
- Colorado Hunting GMUs — Colorado Game Management Units exported to ATAK KMZ; see `projects/colorado-hunting/README.md`.

## Prebuilt maps (no build needed)
- Latest release: <https://github.com/OpenMANET/atakmaps/releases>
- Each project README lists the prebuilt artifact to download (e.g., `MVUM_states.zip`, `USFS_trails.zip`, `CO_GMUs.kmz`, `co_cotrip_cameras_mp.zip`) and how to import it into ATAK.


## Links
This PDF has been invaluable for information on ATAK KML styling, no one else seems to have covered this information, at this level of detail. This is also included in the `/docs` folder, just to ensure it's not lost.
https://mappingsupport.com/p2/atak/pdf/atak_arcgis_tips.pdf
