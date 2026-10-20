import hashlib
import os
import shutil
from datetime import datetime

from lxml import etree


class CotDP():

    def __init__(self, man_name):
        """
        Initializes a new datapackage with a specified manifest name, creating necessary directories
        and setting up an XML structure for a Mission Package Manifest. Individual CoT files will be created
        in the folders, and the Manifest will reference each of them for use in TAK. 

        Args:
            man_name (str): The name of the manifest, used to create directories and as a parameter
                            in the XML configuration.

        Attributes:
            man_name (str): Stores the manifest name.
            man_tree (etree.Element): The root element of the XML structure for the manifest.
            contents (etree.Element): The 'Contents' sub-element of the manifest XML.

        """
        os.system(f'mkdir -p "cache/cot/{man_name}/MANIFEST"')
        os.system(f'mkdir -p "cache/cot/{man_name}/cot"')

        self.man_name = man_name
        self.man_tree = etree.Element("MissionPackageManifest", version="2")
        config = etree.SubElement(self.man_tree, "Configuration")
        # Hashing the manifest name to get the ID lets us rebuild a package with the same ID each time, while still being unique
        config.append( etree.Element("Parameter", name="uid", value=hashlib.md5(man_name.encode()).hexdigest()))
        config.append( etree.Element("Parameter", name="name", value=man_name))
        config.append( etree.Element("Parameter", name="onReceiveImport", value="true"))
        config.append( etree.Element("Parameter", name="onReceiveDelete", value="false"))
        config.append( etree.Element("Parameter", name="callsign", value="Q"))

        self.contents = etree.SubElement(self.man_tree, "Contents")


    def write_manifest(self, dest):
        """
        Writes the XML representation of the mission package manifest to a file.

        Args:
            dest (str): The destination file path where the XML content will be written.
        """
        with open(dest, 'w') as man_file:
          man_file.write('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n')
          man_file.write(etree.tostring(self.man_tree, pretty_print=True).decode())


    def add_to_manifest(self, cot_id):
        """
        Add a single cot ID to the package manifest. Assumes the file is placed at cot/{cot_id}.cot

        Args:
            cot_id (str): The GUID string referencing both the CoT object and it's local file.
        """
        content = etree.SubElement(self.contents, "Content", ignore="false", zipEntry=f"cot/{cot_id}.cot")
        content.append( etree.Element("Parameter", name="uid", value=cot_id))


    def make_cot(self, uid, type, callsign, lat, lon):
        cot_doc = etree.Element("event",
                            version="2.0",
                            uid=uid,
                            type=type,
                            time=datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                            start=datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                            state=datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                            how="m-p")
        cot_doc.append( etree.Element("point", lat=str(lat), lon=str(lon),
                                    hae="999999.0", ce="999999.0", le="999999.0"))
        detail = etree.SubElement(cot_doc, "detail")
        detail.append( etree.Element("status", readiness="true"))
        detail.append( etree.Element("archive"))
        detail.append( etree.Element("contact", callsign=callsign))

        detail.append( etree.Element("color", argb="-1"))
        detail.append( etree.Element("remarks"))
        detail.append( etree.Element("precisionlocation", altsrc="USER"))
        detail.append( etree.Element("uid", nett="XX"))
        detail.append( etree.Element("__special", count="0"))

        return(cot_doc)
    

    def add_video_sensor(self, cot, url, alias, azimuth="0"):
        """
        Adds a video sensor and video link to an existing CoT object. May need to be adjusted to work 
        with sensors other than 511 traffic cameras
        """
        detail = cot.find('detail')

        detail.append( etree.Element("sensor",
                                     fovGreen="1.0",
                                     fovBlue="1.0",
                                     fovRed="1.0",
                                     range="167166",
                                     azimuth=azimuth,
                                     displayMagneticReference="0",
                                     fov="65",
                                     hideFov="true",
                                     fovAlpha="0.3"))
        vid = etree.SubElement(detail, "__video", uid=cot.attrib['uid'], url=url)
        vid.append( etree.Element("ConnectionEntry",
                                  networkTimeout="120000",
                                  uid=cot.attrib['uid'],
                                  protocol="raw",
                                  bufferTime="-1",
                                  address=url,
                                  port="-1",
                                  rtspReliable="0",
                                  ignoreEmbeddedKLV="false",
                                  alias=alias))


    def write_cot(self, cot_doc, dest):
         """
         Write a single CoT object to a file.

         Args:
            cot_doc (etree.Element): The CoT object to write to a file.
            dest (str): The destination file path where the CoT content will be written.
         """
         with open(dest, 'w') as cot_file:
            cot_file.write('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n')
            cot_file.write(etree.tostring(cot_doc, pretty_print=True).decode())


    def zip(self, input_path, output_path):
        """Zips the current cot objects into a datapackage"""



        os.chdir(input_path)
        shutil.make_archive(output_path.removesuffix(".zip"), format('zip'))