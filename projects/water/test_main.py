import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("main.py")
SPEC = importlib.util.spec_from_file_location("water_main", MODULE_PATH)
assert SPEC and SPEC.loader
water = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(water)


class WaterKmlTests(unittest.TestCase):
    def test_alaska_is_split_at_the_antimeridian(self):
        bboxes = water.state_query_bboxes("AK")
        self.assertEqual(len(bboxes), 3)
        self.assertTrue(all(east - west < 40 for west, _, east, _ in bboxes))

    def test_other_states_use_shared_bbox(self):
        self.assertEqual(water.state_query_bboxes("CO"), [water.STATE_BBOXES["CO"]])

    def test_alaska_uses_a_practical_unnamed_waterbody_threshold(self):
        self.assertEqual(
            water.waterbody_queries("AK"),
            ("gnisidlabel IS NOT NULL", "areasqkm >= 0.25"),
        )
        self.assertIn("areasqkm >= 0.02", water.waterbody_queries("CO"))

    def test_arcgis_page_size_shrinks_after_service_error(self):
        requested_sizes = []
        original = water._request_json

        def fake_request(url, params, retries=4):
            requested_sizes.append(params["resultRecordCount"])
            if params["resultRecordCount"] > 500:
                raise water.urllib.error.URLError("response too large")
            return {"features": []}

        water._request_json = fake_request
        try:
            self.assertEqual(
                list(
                    water.fetch_arcgis_features(
                        "https://example.invalid", 60, "1=1", ["OBJECTID"]
                    )
                ),
                [],
            )
        finally:
            water._request_json = original
        self.assertEqual(requested_sizes, [2000, 1000, 500])

    def test_quality_style_priority(self):
        self.assertEqual(water.quality_style({"isassessed": "Y"}), "quality-good")
        self.assertEqual(
            water.quality_style({"isassessed": "Y", "isthreatened": "Y"}),
            "quality-threatened",
        )
        self.assertEqual(
            water.quality_style({"isthreatened": "Y", "isimpaired": "Y"}),
            "quality-impaired",
        )

    def test_quality_description_escapes_values_and_includes_warning(self):
        output = water.quality_description(
            {
                "assessmentunitname": "Creek <North>",
                "isassessed": "Y",
                "pathogens": "Y",
            }
        )
        self.assertIn("Creek &lt;North&gt;", output)
        self.assertIn("Pathogens", output)
        self.assertIn("not a real-time safety or potability test", output)

    def test_kml_geometry_types(self):
        root, document = water.new_document("Test")
        count = water.add_folder(
            document,
            "Features",
            [
                {
                    "type": "Feature",
                    "properties": {"name": "Line"},
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[-105.0, 39.0], [-104.9, 39.1]],
                    },
                },
                {
                    "type": "Feature",
                    "properties": {"name": "Lake"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [[-105.0, 39.0], [-104.9, 39.0], [-105.0, 39.0]]
                        ],
                    },
                },
            ],
            default_style="flowline",
            description_builder=lambda props: props["name"],
            name_fields=("name",),
        )
        self.assertEqual(count, 2)
        text = water.ET.tostring(root, encoding="unicode")
        self.assertIn("LineString", text)
        self.assertIn("Polygon", text)

    def test_false_pollutant_flags_are_not_duplicated_in_extended_data(self):
        root, document = water.new_document("Test")
        water.add_folder(
            document,
            "Assessment",
            [
                {
                    "properties": {"assessmentunitname": "Creek", "pathogens": "N"},
                    "geometry": {"type": "Point", "coordinates": [-105.0, 39.0]},
                }
            ],
            default_style="quality-unknown",
            description_builder=water.quality_description,
            name_fields=("assessmentunitname",),
            dynamic_style=True,
        )
        ns = {"k": water.KML_NS}
        self.assertIsNone(root.find(".//k:Data[@name='pathogens']", ns))


if __name__ == "__main__":
    unittest.main()
