import base64
import json
import os
import shutil
import zipfile
from datetime import datetime
from html import unescape
from pathlib import Path

import requests
from lxml import etree, objectify
from pykml import parser
from pykml.factory import KML_ElementMaker as KML

OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"
TEMP_DIR = OUTPUT_DIR / "temp"

TRUCK_PARKING_ICON_B64 = "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"
MESSAGE_SIGN_ICON_B64 = "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAAAXNSR0IArs4c6QAAAAZiS0dEAP8A/wD/oL2nkwAAAAlwSFlzAAALEwAACxMBAJqcGAAAAAd0SU1FB9oHEBMTAgzJI/EAAABMSURBVFjD7dPRCQAgCEVRFadr4NazFRSSqO75lnr0TAQAfqfF+dh9vlcTx0zePHJzdroCb3r6NGvclzsq0EIF2vEL5KYdIMCbAQAACxR/BxiFL2E7AAAAAElFTkSuQmCC"
    

def truck_parking(name, url):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    (TEMP_DIR / "parking").mkdir(parents=True, exist_ok=True)

    print("Fetching truck parking")

    export = requests.get(url).content
    tld = KML.kml(KML.Document(
        KML.name(name),
        KML.description("Test"),
        KML.Style(
            KML.IconStyle(
                KML.Icon(KML.href('ic_TruckParking.png')),
                KML.hotSpot(x='0.5', y='0.5', xunits='fraction', yunits='fraction')
            ),
            KML.LabelStyle(
                KML.scale(0)
            ),
            id="parking"
        )
    ))

    style = """table, th, td {
        border-bottom: 1px solid #ddd
    }"""
    for stop in json.loads(export):
        tld.Document.append(KML.Placemark(
            KML.name(stop['FacilityName']),
            KML.description(f"""
<style>
{style}
</style>
<table>
  <tr>
    <th>Facility Name</th>
    <td>{stop['FacilityName']}</td>
  </tr>
  <tr>
    <th>Roadway</th>
    <td>{stop['Roadway']}</td>
  </tr>
  <tr>
    <th>Total Parking Spaces</th>
    <td>{stop['TotalParkingSpaces']}</td>
  </tr>
  <tr>
    <th>Available Parking Spaces</th>
    <td>{stop['AvailableParkingSpaces']}</td>
  </tr>
  <tr>
    <th>Trend</th>
    <td>{stop['Trend']}</td>
  </tr>
  <tr>
    <th>Open</th>
    <td>{stop['Open']}</td>
  </tr>
  <tr>
    <th>Amenities</th>
    <td>{stop['Amenities']}</td>
  </tr>
</table>

Last updated {timestamp}
"""),
            KML.styleUrl("#parking"),
            KML.Point(
                KML.coordinates(str(stop['Longitude']) + ',' + str(stop['Latitude'])))
            )
        )

    objectify.deannotate(tld, xsi_nil=True)
    etree.cleanup_namespaces(tld)

    os.chdir('../../..')
    assert(parser.Schema("kml22gx.xsd").validate(tld))
    final_kml_text = etree.tostring(tld, pretty_print=True )
    output = Path(f'{TEMP_DIR}/parking/doc.kml')
    output.write_bytes(final_kml_text)
    with open(f'{TEMP_DIR}/parking/doc.kml', 'w', encoding='utf-8') as outputfile:
        outputfile.write(unescape(final_kml_text.decode()))
    
    # Write truck parking icon from base64 to temp directory
    icon_path = Path(f'{TEMP_DIR}/parking/ic_TruckParking.png')
    icon_path.write_bytes(base64.b64decode(TRUCK_PARKING_ICON_B64))
    
    with zipfile.ZipFile(f'{OUTPUT_DIR}/{name}.kmz',
                         'w', zipfile.ZIP_DEFLATED) as zip:
        os.chdir(f'{TEMP_DIR}/parking/')
        zip.write('doc.kml')
        zip.write('ic_TruckParking.png')

def message_signs(name, url):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    (TEMP_DIR / "messagesigns").mkdir(parents=True, exist_ok=True)

    print("Fetching message signs")

    export = requests.get(url).content
    tld = KML.kml(KML.Document(
        KML.name(name),
        KML.description("Test"),
        KML.Style(
            KML.IconStyle(
                KML.Icon(KML.href('ic_MessageSign.png')),
                KML.hotSpot(x='0.5', y='0.5', xunits='fraction', yunits='fraction')
            ),
            KML.LabelStyle(
                KML.scale(0)
            ),
            id="ms"
        )
    ))
    
    for sign in json.loads(export):
        msg = sign["Messages"][0].replace('\n', '<br>').replace('\t', '&#9;')
        tld.Document.append(KML.Placemark(
            KML.name(sign['Name']),
            KML.description(r"""
<![CDATA[
    <style>
        @font-face{font-family:'Scoreboard';src:url(https://quickmap.dot.ca.gov/ca511dfp/scoreboard.ttf) format('truetype')}
        .cms{min-width:306px;width:fit-content;min-height:105px;height:fit-content;margin:.1em;background-color:#000;text-align:center;white-space:pre}
        .cms1{color:orange;font-family:Scoreboard,Courier New;font-size:35px;line-height:35px}
        .cms2{color:orange;font-family:Scoreboard,Courier New;font-size:35px;line-height:35px}
    </style>                

    <div class='cms_container'>
        <div class='cms cms1'>%s</div>
        <div style='display: none;' class='cms cms2'><br><br></div>
    </div>
    <p class="update-stamp">Last updated: %s</p>
    ]]>
            """ % (msg, timestamp)),
            KML.styleUrl("#ms"),
            KML.Point(
                KML.coordinates(str(sign['Longitude']) + ',' + str(sign['Latitude'])))
            )
        )
    
    objectify.deannotate(tld, xsi_nil=True)
    etree.cleanup_namespaces(tld)

    assert(parser.Schema("kml22gx.xsd").validate(tld))
    final_kml_text = etree.tostring(tld, pretty_print=True)
    
    with open(f'{TEMP_DIR}/messagesigns/doc.kml', 'w', encoding='utf-8') as outputfile:
        outputfile.write(unescape(final_kml_text.decode()))
    
    icon_path = Path(f'{TEMP_DIR}/messagesigns/ic_MessageSign.png')
    icon_path.write_bytes(base64.b64decode(MESSAGE_SIGN_ICON_B64))
    
    with zipfile.ZipFile(f'{OUTPUT_DIR}/{name}.kmz',
                         'w', zipfile.ZIP_DEFLATED) as zip:
        os.chdir(f'{TEMP_DIR}/messagesigns/')
        zip.write('doc.kml')
        zip.write('ic_MessageSign.png')

if __name__ == '__main__':
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    message_signs("WI_511_MessageSigns", f"https://511wi.gov/api/v2/get/messagesigns?key={os.getenv('WI_511_API_KEY', '')}")
    truck_parking("WI_511_TruckParking", f"https://511wi.gov/api/v2/get/truckparking?key={os.getenv('WI_511_API_KEY', '')}")
    
    shutil.rmtree(TEMP_DIR)