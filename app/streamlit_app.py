import streamlit as st
import streamlit.components.v1 as components

# --- 1. SET PAGE CONFIGURATION ---
st.set_page_config(
    layout="wide", 
    page_title="Live Drag Router", 
    initial_sidebar_state="collapsed"
)

# --- 2. AGGRESSIVE STREAMLIT CSS OVERRIDE (FIXES SCROLLING) ---
# This targets the outer Streamlit containers to force full screen and remove scrolling.
st.markdown("""
<style>
    /* Remove default Streamlit padding, margins, and headers */
    #MainMenu, header, footer { visibility: hidden; }
    .stApp { margin: 0; padding: 0; overflow: hidden; height: 100vh; width: 100vw; }
    .main { margin: 0; padding: 0; overflow: hidden; height: 100vh; width: 100vw; }
    .block-container {
        padding: 0 !important;
        margin: 0 !important;
        max-width: 100vw !important;
        height: 100vh !important;
    }
    /* Ensure the Streamlit component iframe and container fill everything */
    [data-testid="stVerticalBlock"] { height: 100vh; width: 100vw; overflow: hidden; }
    [data-testid="stVerticalBlockBorderWrapper"] { height: 100vh; width: 100vw; overflow: hidden; }
    iframe { height: 100vh !important; width: 100vw !important; border: none !important; }
</style>
""", unsafe_allow_html=True)

# --- CONFIGURATION: PUT YOUR API URL HERE ---
API_URL = "http://localhost:8000/route" 
# For testing: API_URL = "https://router.project-osrm.org/route/v1/driving" 

# --- JAVASCRIPT & HTML APPLICATION (Unchanged Logic) ---
# The internal component CSS already forces 100vh/100vw, but is now enforced by the outer container.

html_code = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <link href="https://fonts.googleapis.com/css2?family=Open+Sans:wght@400;600;700&display=swap" rel="stylesheet">
    
    <style>
        /* FULL SCREEN & NO SCROLLING inside iframe */
        html, body, #map-container {{ height: 100vh; width: 100vw; margin: 0; padding: 0; overflow: hidden; }}
        #map-wrapper {{ 
            position: absolute; top: 0; right: 0; bottom: 0; 
            left: 320px; /* Initial space for sidebar */
            transition: left 0.3s; 
            height: 100vh; /* Ensure map fills vertical space */
        }}
        #map {{ height: 100%; width: 100%; }}

        /* OSRM Sidebar Style */
        .sidebar {{
            position: fixed; top: 0; left: 0;
            width: 320px; height: 100vh;
            background: white; z-index: 1000;
            box-shadow: 2px 0 10px rgba(0,0,0,0.1);
            display: flex; flex-direction: column;
            transition: transform 0.3s, opacity 0.3s;
        }}
        
        /* HIDDEN STATE */
        .sidebar.hidden {{ transform: translateX(-320px); opacity: 0; }}

        .header {{
            background: #2d3436; color: white; padding: 15px;
            font-weight: 700; display: flex; align-items: center; justify-content: space-between;
        }}
        
        /* Hide Button */
        .hide-btn {{
            background: none; border: none; color: white;
            font-size: 16px; cursor: pointer; padding: 0 5px;
            transition: color 0.2s;
        }}
        .hide-btn:hover {{ color: #ccc; }}
        
        /* Input & Results Styles */
        .inputs {{ background: #f8f9fa; padding: 15px; border-bottom: 1px solid #ddd; }}
        .input-row {{
            background: white; border: 1px solid #ccc; border-radius: 4px;
            padding: 8px; margin-bottom: 8px; display: flex; align-items: center;
            font-size: 13px; color: #555;
        }}
        .marker-icon {{ width: 16px; height: 16px; border-radius: 50%; margin-right: 10px; flex-shrink: 0; }}
        .marker-A {{ background-color: #2ecc71; }}
        .marker-B {{ background-color: #e74c3c; }}
        
        .results {{ padding: 20px; }}
        .stat-card {{
            border-left: 4px solid #2d3436; background: #fff;
            padding: 10px; border: 1px solid #eee; border-left-width: 4px;
        }}
        .stat-time {{ font-size: 24px; font-weight: bold; color: #333; }}
        .stat-dist {{ color: #777; font-size: 14px; }}
        .loader {{ color: #007bff; font-size: 12px; display: none; margin-top:5px; }}
        
        /* Custom Map Markers */
        .custom-div-icon {{
            width: 20px !important;
            height: 20px !important;
            border-radius: 50%;
            border: 2px solid white;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            font-size: 12px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.3);
        }}
        .icon-a {{
            background-color: #2ecc71 !important;
            color: white;
        }}
        .icon-b {{
            background-color: #e74c3c !important;
            color: white;
        }}
        
        /* Unhide Button (When Sidebar is hidden) */
        .unhide-btn {{
            position: fixed; top: 10px; left: 10px;
            z-index: 1001; background: #2d3436; color: white;
            border: none; padding: 8px 12px; border-radius: 4px;
            cursor: pointer; display: none;
        }}
    </style>
</head>
<body>

    <button id="unhide-btn" class="unhide-btn" onclick="toggleSidebar()">▶ Show Directions</button>

    <div id="sidebar" class="sidebar">
        <div class="header">
            Drag Router
            <div style="display: flex; align-items: center;">
                <div id="loader" class="loader" style="margin-right: 10px;">Updating...</div>
                <button class="hide-btn" onclick="toggleSidebar()">&#9664;</button> </div>
        </div>
        <div class="inputs">
            <div style="padding: 10px; border-bottom: 1px solid #ddd;">
                <label style="font-size: 12px; color: #666; display: block; margin-bottom: 5px;">Search Mode</label>
                <select id="search-mode" style="width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; font-size: 13px;">
                    <option value="radius">Radius</option>
                    <option value="knn">KNN (K-Nearest)</option>
                </select>
            </div>
            <div style="padding: 10px; border-bottom: 1px solid #ddd;" id="radius-container">
                <label style="font-size: 12px; color: #666; display: block; margin-bottom: 5px;">Search Radius (m)</label>
                <input type="number" id="search-radius" value="500" min="50" max="2000" step="50" style="width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; font-size: 13px;">
            </div>
            <div style="padding: 10px; border-bottom: 1px solid #ddd;" id="knn-container" style="display: none;">
                <label style="font-size: 12px; color: #666; display: block; margin-bottom: 5px;">K (Number of Candidates)</label>
                <input type="number" id="num-candidates" value="5" min="1" max="20" step="1" style="width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; font-size: 13px;">
            </div>
            <div style="padding: 10px; border-bottom: 1px solid #ddd;">
                <label style="font-size: 12px; color: #666; display: block; margin-bottom: 5px;">Dataset</label>
                <select id="dataset-selector" style="width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; font-size: 13px;">
                    <option value="Burnaby">Burnaby, Canada</option>
                    <option value="Somerset">Somerset, UK</option>
                </select>
            </div>
            <div class="input-row">
                <div class="marker-icon marker-A"></div>
                <div id="coord-a">Drag marker A</div>
            </div>
            <div class="input-row">
                <div class="marker-icon marker-B"></div>
                <div id="coord-b">Drag marker B</div>
            </div>
        </div>
        <div class="results" id="results-area">
            <div class="stat-card">
                <div class="stat-time" id="disp-time">0 min</div>
                <div class="stat-dist" id="disp-dist">0 km</div>
            </div>
        </div>
    </div>
    
    <div id="map-wrapper">
        <div id="map"></div>
    </div>

    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

    <script>
        // --- DOM ELEMENTS ---
        const sidebar = document.getElementById('sidebar');
        const mapWrapper = document.getElementById('map-wrapper');
        const unhideBtn = document.getElementById('unhide-btn');
        const loader = document.getElementById('loader');

        // --- TOGGLE LOGIC ---
        function toggleSidebar() {{
            const isHidden = sidebar.classList.toggle('hidden');
            if (isHidden) {{
                mapWrapper.style.left = '0'; // Map takes full width
                unhideBtn.style.display = 'block';
            }} else {{
                mapWrapper.style.left = '320px'; // Map respects sidebar width
                unhideBtn.style.display = 'none';
            }}
            // Must invalidate size to redraw the map layers correctly after map size changes
            setTimeout(() => {{ map.invalidateSize(); }}, 300); 
        }}

        // --- 1. SETUP MAP ---
        var map = L.map('map', {{ zoomControl: false }}).setView([49.23, -122.96], 13);
        L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
            attribution: '&copy; OpenStreetMap contributors'
        }}).addTo(map);

        // --- 2. MARKER SETUP ---
        var iconA = L.divIcon({{ className: 'custom-div-icon icon-a', html: '', iconSize: [20, 20], iconAnchor: [10, 10] }});
        var iconB = L.divIcon({{ className: 'custom-div-icon icon-b', html: '', iconSize: [20, 20], iconAnchor: [10, 10] }});

        var markerA = L.marker([49.23, -122.97], {{ icon: iconA, draggable: true }}).addTo(map);
        var markerB = L.marker([49.24, -122.95], {{ icon: iconB, draggable: true }}).addTo(map);
        
        var routeLayer = null;
        
        // --- 2b. DATASET CONFIGURATION ---
        const datasetConfig = {{
            'Burnaby': {{
                center: [49.23, -122.96],
                zoom: 13,
                name: 'Burnaby, Canada'
            }},
            'Somerset': {{
                center: [37.08, -84.61],
                zoom: 13,
                name: 'Somerset, UK'
            }}
        }};

        // --- 3. API FUNCTION ---
        async function fetchRoute(latA, lonA, latB, lonB) {{
            loader.style.display = 'block';
            
            // Get selected parameters
            const dataset = document.getElementById('dataset-selector').value;
            const searchMode = document.getElementById('search-mode').value;
            const searchRadius = document.getElementById('search-radius').value;
            const numCandidates = document.getElementById('num-candidates').value;

            // Build URL based on search mode
            let url = `{API_URL}?source_lat=${{latA}}&source_lon=${{lonA}}&target_lat=${{latB}}&target_lon=${{lonB}}&dataset=${{dataset}}`;
            
            if (searchMode === 'radius') {{
                url += `&search_mode=radius&search_radius=${{searchRadius}}&num_candidates=${{numCandidates}}`;
            }} else {{
                url += `&search_mode=knn&num_candidates=${{numCandidates}}`;
            }}

            try {{
                const response = await fetch(url);
                const data = await response.json();
                
                if (routeLayer) map.removeLayer(routeLayer);

                var routeCoords = [];
                var dist = 0;
                var runtime = 0;

                // Parse shortest path engine response (GeoJSON format)
                if (data.geojson && data.geojson.features && data.geojson.features.length > 0) {{
                    data.geojson.features.forEach(feature => {{
                        if (feature.geometry.type === 'LineString') {{
                            feature.geometry.coordinates.forEach(coord => {{
                                routeCoords.push([coord[1], coord[0]]); // GeoJSON is [lon,lat], Leaflet needs [lat,lon]
                            }});
                        }}
                    }});
                    dist = data.distance || 0;
                    runtime = data.runtime_ms || 0;
                }}

                if (routeCoords.length > 0) {{
                    routeLayer = L.polyline(routeCoords, {{
                        color: '#0066cc', 
                        weight: 5, 
                        opacity: 0.8
                    }}).addTo(map);
                }}
                
                // Display distance and query time
                if (data.success === false) {{
                    document.getElementById('disp-time').innerText = "No route";
                    document.getElementById('disp-dist').innerText = data.error || "Path not found";
                }} else {{
                    document.getElementById('disp-dist').innerText = (dist > 1000) ? (dist/1000).toFixed(2) + ' km' : dist.toFixed(0) + ' m';
                    document.getElementById('disp-time').innerText = runtime.toFixed(2) + ' ms';
                }}
            }} catch (e) {{
                console.error("Routing error:", e);
                document.getElementById('disp-time').innerText = "API Error";
                document.getElementById('disp-dist').innerText = "Check Console";
            }} finally {{
                loader.style.display = 'none';
            }}
        }}

        // --- 4. DRAG EVENT LISTENERS ---
        function onDragStart() {{
            // Remove the route immediately when dragging starts
            if (routeLayer) {{
                map.removeLayer(routeLayer);
                routeLayer = null;
            }}
        }}

        function onDrag() {{
            var posA = markerA.getLatLng();
            var posB = markerB.getLatLng();

            // Update Input Text
            document.getElementById('coord-a').innerText = posA.lat.toFixed(5) + ', ' + posA.lng.toFixed(5);
            document.getElementById('coord-b').innerText = posB.lat.toFixed(5) + ', ' + posB.lng.toFixed(5);

            // Fetch new route
            fetchRoute(posA.lat, posA.lng, posB.lat, posB.lng);
        }}

        markerA.on('dragstart', onDragStart);
        markerB.on('dragstart', onDragStart);
        markerA.on('dragend', onDrag);
        markerB.on('dragend', onDrag);

        // --- 5. DATASET CHANGE HANDLER ---
        document.getElementById('dataset-selector').addEventListener('change', function() {{
            const newDataset = this.value;
            const config = datasetConfig[newDataset];
            
            // Update map center and zoom
            map.setView(config.center, config.zoom);
            
            // Reset markers to dataset center
            markerA.setLatLng([config.center[0] - 0.01, config.center[1] - 0.01]);
            markerB.setLatLng([config.center[0] + 0.01, config.center[1] + 0.01]);
            
            // Recalculate route with new dataset
            onDrag();
        }});

        // --- 6. SEARCH MODE CHANGE HANDLER ---
        document.getElementById('search-mode').addEventListener('change', function() {{
            const mode = this.value;
            const radiusContainer = document.getElementById('radius-container');
            const knnContainer = document.getElementById('knn-container');
            
            if (mode === 'radius') {{
                radiusContainer.style.display = 'block';
                knnContainer.style.display = 'none';
            }} else {{
                radiusContainer.style.display = 'none';
                knnContainer.style.display = 'block';
            }}
            
            // Recalculate route with new search mode
            onDrag();
        }});

        // --- 7. PARAMETER CHANGE HANDLERS ---
        document.getElementById('search-radius').addEventListener('change', onDrag);
        document.getElementById('num-candidates').addEventListener('change', onDrag);

        // Initial Call
        onDrag();
    </script>
</body>
</html>
"""

# Inject the component (removed height=900)
# We use max height/width properties on the containers instead.
components.html(html_code, width=2000, height=9999, scrolling=False)