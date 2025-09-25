
import os
import traceback
import streamlit as st
import ee
import json
from streamlit_folium import st_folium
import folium
from folium.plugins import Draw, MeasureControl


st.set_page_config(layout="wide", page_title="Accurate Pest Detection System (Draw Field)")


def try_initialize_ee(project_id=None):
    try:
       
        if project_id:
            ee.Initialize(project=project_id)
        else:
            ee.Initialize(project="*/enter your project id/*")  
        return True, "EE INITIALIZED OK"
    except Exception as e:
        tb = traceback.format_exc()
        return False, f"{str(e)}\n\nTraceback:\n{tb}"


if "ee_init_done" not in st.session_state:
    proj = os.environ.get("EARTHENGINE_PROJECT", None)
    ok, msg = try_initialize_ee(proj)
    st.session_state["ee_init_done"] = ok
    st.session_state["ee_init_msg"] = msg
else:
    ok = st.session_state["ee_init_done"]
    msg = st.session_state["ee_init_msg"]

if not ok:
    st.error(
        "Earth Engine not initialized. Run 'earthengine authenticate' in the SAME terminal, "
        "ensure the project is registered & Earth Engine API enabled."
    )
    with st.expander("Show Earth Engine error details"):
        st.code(msg)
    st.stop()


st.title("Accurate Pest Detection System — Draw Field on Map (Sentinel-2)")
st.markdown(
    "Draw your field polygon on the map (use the draw tools on the top-left). "
    "After drawing, click **Use Drawn Polygon** and then **Run Pest Detection**."
)


st.sidebar.header("Parameters")
season_start = st.sidebar.text_input("Season start (YYYY-MM-DD)", value="2025-06-01")
season_end = st.sidebar.text_input("Season end (YYYY-MM-DD)", value="2025-10-01")
baseline_years_text = st.sidebar.text_input(
    "Baseline years (comma sep)", value="2019,2020,2021,2022,2023"
)
ndvi_threshold = st.sidebar.number_input(
    "NDVI anomaly threshold (negative)", value=-0.10, step=0.01
)
min_frac = st.sidebar.number_input(
    "Min fraction of pixels below threshold", value=0.10, step=0.05
)
consecutive_needed = st.sidebar.number_input(
    "Consecutive observations needed", value=2, step=1
)


def parse_years(text):
    parts = [p.strip() for p in text.split(",") if p.strip()]
    years = []
    for p in parts:
        try:
            years.append(int(p))
        except:
            pass
    return years


col_map, col_ctrl = st.columns([3, 1])

with col_map:
  
    m = folium.Map(location=[23.0, 77.5], zoom_start=8, control_scale=True)

    
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(m)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri",
        name="Esri Satellite",
        overlay=False,
        control=True,
    ).add_to(m)
    folium.TileLayer(
        "CartoDB positron",
        name="Carto Light",
        overlay=False,
        control=True,
    ).add_to(m)

    folium.LayerControl().add_to(m)

    
    draw = Draw(
        export=True,
        draw_options={
            "polyline": False,
            "polygon": True,
            "circle": False,
            "rectangle": True,
            "marker": False,
            "circlemarker": False,
        },
        edit_options={"edit": True},
    )
    draw.add_to(m)

    
    m.add_child(
        MeasureControl(
            primary_length_unit="meters",
            secondary_length_unit="kilometers",
            primary_area_unit="sqmeters",
            secondary_area_unit="hectares",
        )
    )

    st.write("**Draw polygon on the map** — then click Save/Export in the toolbar.")
    map_data = st_folium(m, height=600)

with col_ctrl:
    st.write("### Controls")
    uploaded = st.file_uploader(
        "Or upload GeoJSON (optional)", type=["geojson"], key="geojson_upload"
    )
    use_drawn = st.button("Use Drawn Polygon", key="btn_drawn")
    use_sample = st.button("Use Sample Polygon (Test)", key="btn_sample")
    run = st.button("Run Pest Detection", key="btn_run")


if "drawn_geom" not in st.session_state:
    st.session_state["drawn_geom"] = None

if use_drawn:
    captured = None
    if map_data and isinstance(map_data, dict):
        captured = map_data.get("last_active_drawing")
        if (not captured) and map_data.get("all_drawings"):
            all_d = map_data.get("all_drawings")
            if isinstance(all_d, list) and len(all_d) > 0:
                captured = all_d[-1]
    if isinstance(captured, dict) and captured.get("geometry"):
        st.session_state["drawn_geom"] = captured["geometry"]
        st.success("✅ Drawn polygon saved.")
    else:
        st.error(" No drawn polygon detected. Make sure you saved/exported in the toolbar.")

geom = None
if uploaded is not None:
    try:
        gj = json.load(uploaded)
        if "features" in gj and len(gj["features"]) > 0:
            geom = gj["features"][0]["geometry"]
        elif gj.get("type", "").lower() == "feature":
            geom = gj["geometry"]
        else:
            st.error("Uploaded GeoJSON invalid (no Feature found).")
    except Exception:
        st.error("Invalid GeoJSON uploaded.")
elif st.session_state.get("drawn_geom") is not None:
    geom = st.session_state["drawn_geom"]
elif use_sample:
    geom = {
        "type": "Polygon",
        "coordinates": [
            [[77.5, 23.0], [77.6, 23.0], [77.6, 23.1], [77.5, 23.1], [77.5, 23.0]]
        ],
    }


if geom is not None:
    st.success("Polygon loaded. You can now press **Run Pest Detection**.")
    st.json(geom)

    try:
        g = ee.Geometry(geom)
        area_ha = g.area(maxError=1).divide(10000).getInfo()
        perimeter_m = g.perimeter(maxError=1).getInfo()
        st.info(f"📏 Area: {area_ha:.2f} hectares | Perimeter: {perimeter_m:.2f} meters")
    except Exception:
        st.warning("Could not calculate area/perimeter. Try again.")


def compute_decision(
    geom, season_start, season_end, baseline_years, ndvi_threshold, min_frac, consecutive_needed
):
    feature = ee.Feature(ee.Geometry(geom))
    fields = ee.FeatureCollection([feature])

    baseline_col = [
        ee.ImageCollection("COPERNICUS/S2_SR")
        .filterDate(f"{y}-06-01", f"{y}-10-01")
        .filterBounds(fields)
        .map(lambda img: img.normalizedDifference(["B8", "B4"]).rename("NDVI"))
        .median()
        for y in baseline_years
    ]
    baseline = ee.ImageCollection(baseline_col).median().rename("NDVI_baseline")

    season_col = (
        ee.ImageCollection("COPERNICUS/S2_SR")
        .filterDate(season_start, season_end)
        .filterBounds(fields)
        .map(lambda img: img.normalizedDifference(["B8", "B4"]).rename("NDVI"))
        .sort("system:time_start")
    )

    imgs = season_col.toList(season_col.size())
    n = imgs.size().getInfo()
    if n == 0:
        return {"error": "No Sentinel-2 images available for this season/area."}

    anom_list = []
    baseline_mean = (
        baseline.reduceRegion(
            ee.Reducer.mean(), geometry=feature.geometry(), scale=10, maxPixels=1e9
        )
        .get("NDVI_baseline")
        .getInfo()
    )
    for i in range(n):
        img = ee.Image(imgs.get(i))
        mean_ndvi = (
            img.reduceRegion(
                ee.Reducer.mean(), geometry=feature.geometry(), scale=10, maxPixels=1e9
            )
            .get("NDVI")
            .getInfo()
        )
        if mean_ndvi is None or baseline_mean is None:
            anom = None
        else:
            anom = mean_ndvi - baseline_mean
        anom_list.append(anom)

    recent_window = min(5, len([a for a in anom_list if a is not None]))
    last_anoms = [a for a in anom_list[-recent_window:] if a is not None]
    flags = [1 if (a <= ndvi_threshold) else 0 for a in last_anoms]
    consec = False
    if len(flags) >= consecutive_needed:
        for i in range(len(flags) - consecutive_needed + 1):
            if sum(flags[i : i + consecutive_needed]) == consecutive_needed:
                consec = True
                break

    recent_img = ee.Image(imgs.get(n - 1))
    anom_img = recent_img.subtract(baseline)
    try:
        pix_below = (
            anom_img.lt(ndvi_threshold)
            .selfMask()
            .reduceRegion(
                ee.Reducer.count(), geometry=feature.geometry(), scale=10, maxPixels=1e9
            )
            .values()
            .get(0)
            .getInfo()
        )
        pix_tot = (
            recent_img.reduceRegion(
                ee.Reducer.count(), geometry=feature.geometry(), scale=10, maxPixels=1e9
            )
            .values()
            .get(0)
            .getInfo()
        )
    except Exception:
        pix_below = None
        pix_tot = None
    frac = None
    if pix_below is not None and pix_tot is not None and pix_tot > 0:
        frac = pix_below / pix_tot

    decision = consec and (frac is not None) and (frac >= min_frac)
    return {
        "n_images": n,
        "last_anoms": last_anoms,
        "consecutive_flag": consec,
        "pix_below": pix_below,
        "pix_tot": pix_tot,
        "frac": frac,
        "pest_detected": decision,
    }


if run:
    if geom is None:
        st.error("No polygon selected. Draw polygon, press 'Use Drawn Polygon' or upload GeoJSON.")
    else:
        baseline_years = parse_years(baseline_years_text)
        if len(baseline_years) == 0:
            st.error("Invalid baseline years.")
        else:
            with st.spinner("Running analysis... this may take 30s-2min"):
                try:
                    res = compute_decision(
                        geom,
                        season_start,
                        season_end,
                        baseline_years,
                        ndvi_threshold,
                        min_frac,
                        consecutive_needed,
                    )
                except Exception:
                    st.error("Error during Earth Engine computation.")
                    st.expander("EE error details").write(traceback.format_exc())
                    st.stop()

            if "error" in res:
                st.error(res["error"])
            else:
                st.write(res)
                if res["pest_detected"]:
                    st.error("🚨 Pest Detected!")
                else:
                    st.success("✅ No pest detected.")
                st.balloons()
