import hashlib
import json
import os
import shutil
from html import unescape
from pathlib import Path

import requests
from cot import CotDP

OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"
DP_PATH = OUTPUT_DIR / "WI_511_Cameras.zip"
TEMP_DIR = OUTPUT_DIR / "temp"
URL_WI511 = "https://511wi.gov/api/v2/get/cameras?key=" + os.getenv('WI_511_API_KEY', '')

def traffic_cams_wi(name, url):
    cot_dir = TEMP_DIR / "cot"
    man_dir = TEMP_DIR / "MANIFEST"
    cot_dir.mkdir(parents=True, exist_ok=True)
    man_dir.mkdir(parents=True, exist_ok=True)

    print("Fetching traffic cameras")

    export = requests.get(url).content
    dp = CotDP(name)

    try:
        for cam in json.loads(export):
            cam_id = hashlib.md5(str(cam["Id"]).encode()).hexdigest()
            cot = dp.make_cot(cam_id, 'b-m-p-s-p-loc', cam['Location'], cam['Latitude'], cam['Longitude'])
            dp.add_to_manifest(cam_id)
            for view in cam["Views"]:
                dp.add_video_sensor(cot, view['VideoUrl'], cam['Location'])
            dp.write_cot(cot, f'{cot_dir}/{cam_id}.cot')
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        print(export)
        exit(1)

    dp.write_manifest(f'{man_dir}/manifest.xml')
    dp.zip(f'{TEMP_DIR}', f'{DP_PATH}')


if __name__ == '__main__':
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    traffic_cams_wi("WI_511_Cameras", f"https://511wi.gov/api/v2/get/cameras?key={os.getenv('WI_511_API_KEY', '')}")
    
    shutil.rmtree(TEMP_DIR)