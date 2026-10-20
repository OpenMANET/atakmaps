# ATAK Map Projects
-----------------

This repo holds various ATAK-related map projects and may drift over time as different data/maps are used. Each project lives in its own folder under `projects/`.

## Map source

**Use <https://openmanet.github.io/atakmaps/> as the authoritative source for current, ready-to-import map files.** The catalog is rebuilt by CI/CD and lists every published KMZ or data package. GitHub Releases are not used for distribution.

## Projects
- USFS MVUM — exports Motor Vehicle Use Map data to ATAK-ready KML/KMZ with access legends; see `projects/mvum/readme.md`.
- USFS Trails (non-motorized) — per-state KMZs for hiking/bike/snow trails from TrailNFS_Publish, with motorized segments removed; see `projects/usfs/readme.md`.
- Colorado CoTrip traffic cameras — CoTrip camera feeds packaged for ATAK data packages; see `projects/colorado-traffic-cameras/README.md`.
- Colorado Hunting GMUs — Colorado Game Management Units exported to ATAK KMZ; see `projects/colorado-hunting/README.md`.
- USGS Surface Water + EPA Water Quality — separate ATAK KMZ overlays for 3DHP streams, lakes, waterbodies, and springs plus ATTAINS assessment status; see `projects/water/README.md`.

## Prebuilt maps (no build needed)
- Browse or download current files from <https://openmanet.github.io/atakmaps/>.
- Each project README describes its published filenames and how to import them into ATAK.

## Network link KMZ for ATAK
- The scheduled workflow `.github/workflows/build-kmz.yml` builds KMZs weekly and publishes them to the authoritative source at <https://openmanet.github.io/atakmaps/> (manual trigger: `gh workflow run build-kmz.yml`).
- Pages URL pattern: `https://openmanet.github.io/atakmaps/mvum/MVUM_KY.kmz` (e.g., `.../mvum/MVUM_CO.kmz` or `.../mvum/MVUM_states.zip`).
- State water overlays use `https://openmanet.github.io/atakmaps/water/USGS_3DHP_CO.kmz` and `https://openmanet.github.io/atakmaps/water/EPA_ATTAINS_CO.kmz`; replace `CO` with any state or D.C. abbreviation.
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
- Alternate import paths in ATAK (Select Import Type): Local SD, Gallery, KML Link, HTTP URL, or Choose App. Pick the one that fits how you’re grabbing the KMZ/KML.


## Links
This PDF has been invaluable for information on ATAK KML styling, no one else seems to have covered this information, at this level of detail. This is also included in the `/docs` folder, just to ensure it's not lost.
https://mappingsupport.com/p2/atak/pdf/atak_arcgis_tips.pdf
