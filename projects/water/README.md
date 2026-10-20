# USGS Surface Water + EPA Water Quality → ATAK

This project builds two complementary ATAK KMZ overlays per state:

- `USGS_3DHP_CO.kmz` — named streams/flowlines, lakes, ponds, reservoirs, larger unnamed waterbodies, and springs from the U.S. Geological Survey 3D Hydrography Program (3DHP).
- `EPA_ATTAINS_CO.kmz` — state-reported surface-water assessment status and summarized concerns from EPA ATTAINS.

Tap a feature in ATAK to see an HTML summary similar to the USFS overlays. The EPA layer uses green for assessed features not flagged impaired, orange for threatened features, red for impaired/listed features, and gray where assessment status is unavailable.

## Data sources

- USGS 3DHP Feature Service: <https://3dhp.nationalmap.gov/arcgis/rest/services/usgs_3dhp_all/FeatureServer>
- EPA ATTAINS Assessment Feature Service used by the builder: <https://services.arcgis.com/cJ9YHowT8TU7DUyn/ArcGIS/rest/services/ATTAINS_Assessment/FeatureServer>
- EPA canonical geospatial service: <https://gispub.epa.gov/arcgis/rest/services/OW/ATTAINS_Assessment/MapServer>
- EPA background and limitations: <https://www.epa.gov/waterdata/get-data-access-public-attains-data>

3DHP is the maintained successor to the retired National Hydrography Dataset. Its service combines newer elevation-derived hydrography where available with NHD data elsewhere. To keep the KMZ usable in ATAK, the flowline overlay includes named segments at least 0.5 km long; waterbodies include named features plus unnamed features at least 0.02 square km (about 5 acres). Alaska retains all named waterbodies but uses 0.25 square km for unnamed polygons because the national service contains hundreds of thousands of tiny Alaska polygons. State bounding boxes are rectangular, so a few features just across a state line may be included.

ATTAINS contains the latest assessment information submitted by each state, territory, or authorized tribe, but reporting cycles and coverage vary. An unassessed, unlisted, or green feature is **not** a real-time safety or potability determination. The EPA overlay should be treated as context, not proof that water is safe.

## Build

Python 3 is the only requirement.

```bash
python3 projects/water/main.py
```

Colorado is the default. Another state can be selected with its two-letter code:

```bash
python3 projects/water/main.py --state WY
```

Use `--skip-usgs` or `--skip-epa` to build only one source. Outputs are written to `projects/water/outputs/`.

## Continuous delivery

The GitHub Actions workflow builds both overlays for all 50 states and Washington, D.C. A four-job concurrency limit avoids flooding the USGS and EPA services. Each state is uploaded as an intermediate artifact, merged into `site/water/`, listed on the generated download page, and published through GitHub Pages. Alaska is queried with two envelopes split at the antimeridian rather than one near-global bounding box.

Published filenames follow these patterns:

- `https://openmanet.github.io/atakmaps/water/USGS_3DHP_{STATE}.kmz`
- `https://openmanet.github.io/atakmaps/water/EPA_ATTAINS_{STATE}.kmz`

For example, Colorado is available as `USGS_3DHP_CO.kmz` and `EPA_ATTAINS_CO.kmz` after a successful deployment.

## ATAK use

Import one or both KMZs through ATAK Data Packages. Keeping hydrography and assessment status in separate files lets either layer be toggled or removed independently. The USGS file can be large; import only the states needed.
