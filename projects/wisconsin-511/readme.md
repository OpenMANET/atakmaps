# Wisconsin 511

These scripts create a datapackage and KMZ files for wisconsin's highway cameras, road signs, and truck parking. `WI_511_Cameras.py` will create a datapackage zip for import into ATAK using native video sensors, allowing the user to view video streams directly within the app. `WI_511_Signs_and_Parking.py` exports 2 separate KMZ files.

## Requirements

You will need an API key from [https://511wi.gov/](https://511wi.gov/). The key is free and you do not need to be a Wisconsin resident to request one. The script looks for the key in an environment variable, so either run `export WI_511_API_KEY=<key>` or use a secure environment file.

Required python packages can be installed with `pip install -r requirements.txt`

## Notes

WI511 makes some other interesting information avaialable like winter road conditions that may be valuable to add.
