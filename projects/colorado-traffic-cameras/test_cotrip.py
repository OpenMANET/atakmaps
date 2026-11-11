import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("cotrip.py")
SPEC = importlib.util.spec_from_file_location("cotrip", MODULE_PATH)
assert SPEC and SPEC.loader
cotrip = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cotrip)


class CoTripInventoryTests(unittest.TestCase):
    def test_filters_broken_and_non_hls_views(self):
        camera = cotrip.camera_from_feature(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [-105.0, 39.7]},
                "properties": {
                    "id": 42,
                    "name": "Test Camera",
                    "public": True,
                    "views": [
                        {"name": "Live", "type": "WMP", "url": "https://example/live.m3u8", "broken": False},
                        {"name": "Broken", "type": "WMP", "url": "https://example/broken.m3u8", "broken": True},
                        {"name": "Still", "type": "STILL_IMAGE", "url": "https://example/image.jpg", "broken": False},
                    ],
                },
            }
        )
        self.assertIsNotNone(camera)
        self.assertEqual(camera["uri"], "camera/42")
        self.assertEqual(
            [source["src"] for source in camera["hls_sources"]],
            ["https://example/live.m3u8"],
        )
        self.assertTrue(camera["active"])

    def test_keeps_still_only_camera_without_hls(self):
        camera = cotrip.camera_from_feature(
            {
                "geometry": {"type": "Point", "coordinates": [-104.9, 39.6]},
                "properties": {"id": 7, "name": "Still", "views": []},
            }
        )
        self.assertEqual(camera["hls_sources"], [])
        self.assertFalse(camera["active"])

    def test_inventory_is_sorted_by_numeric_camera_id(self):
        def feature(camera_id):
            return {
                "geometry": {"type": "Point", "coordinates": [-105.0, 39.0]},
                "properties": {"id": camera_id, "views": []},
            }

        inventory = cotrip.build_inventory(
            {"features": [feature(20), feature(3), feature(100)]}
        )
        self.assertEqual(
            [camera["uri"] for camera in inventory],
            ["camera/3", "camera/20", "camera/100"],
        )


if __name__ == "__main__":
    unittest.main()
