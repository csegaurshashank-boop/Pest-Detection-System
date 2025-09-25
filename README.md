Accurate Pest Detection Project — Sentinel-2 (GEE) + Streamlit Demo

Overview:
This package provides a local Streamlit app that accepts a field polygon (GeoJSON) and runs an NDVI-anomaly-based
pest detection using the Google Earth Engine (GEE) Python API. It implements conservative decision rules:
- NDVI anomaly mean below threshold AND
- minimum fraction of pixels below threshold (min_frac) AND
- persistence across consecutive observations (consecutive_needed).

Files:
- app.py                   : Streamlit application (run locally)
- requirements.txt         : Python packages to install
- gee_auth_instructions.txt: How to authenticate Earth Engine
- gee_script_improved.js   : GEE Code Editor script for reference
- sample_field.geojson     : Sample polygon for testing
- slides_short.md          : Slide content (markdown)
- report_short.md          : Short report text
- README.md                : This file
