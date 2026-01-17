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

## Network link KMZ for ATAK
- The scheduled workflow `.github/workflows/build-kmz.yml` builds KMZs weekly and publishes them to GitHub Pages (manual trigger: `gh workflow run build-kmz.yml`).
- Pages URL pattern: `https://openmanet.github.io/atakmaps/mvum/MVUM_KY.kmz` (e.g., `.../mvum/MVUM_CO.kmz` or `.../mvum/MVUM_states.zip`).
- Create a small KML that references the hosted KMZ, then zip it to KMZ and import into ATAK. Example:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>MVUM CO (network link)</name>
    <NetworkLink>
      <name>MVUM CO</name>
      <Link>
        <href>https://openmanet.github.io/atakmaps/mvum/MVUM_CO.kmz</href>
        <refreshMode>onInterval</refreshMode>
        <refreshInterval>3600</refreshInterval>
      </Link>
    </NetworkLink>
  </Document>
</kml>
```
- Zip that KML into a KMZ and import it in ATAK (Data > Import or Network Links > Add). ATAK will pull fresh KMZs from GitHub Pages on each refresh.
- ATAK UI steps to add a network KMZ: ATAK → Tools (hammer/wrench) → Data Packages → Network Links → `+` → pick the KMZ file; set refresh to 1 hour; save. The link will auto-refresh from the hosted KMZ.


## Links
This PDF has been invaluable for information on ATAK KML styling, no one else seems to have covered this information, at this level of detail. This is also included in the `/docs` folder, just to ensure it's not lost.
https://mappingsupport.com/p2/atak/pdf/atak_arcgis_tips.pdf
