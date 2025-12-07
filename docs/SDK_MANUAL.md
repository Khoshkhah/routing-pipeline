# Routing SDK Manual

The `routing-pipeline` project includes a Python SDK for interacting with the high-performance C++ Routing Server.

## 📦 Installation

The SDK is part of the `routing-pipeline` package. Ensure dependencies are installed:

```bash
cd routing-pipeline
pip install -r api/requirements.txt
```

## 🚀 Quick Start

### 1. Connect to the Server

Use the `CHQueryEngineFactory` to create a client connected to your running `routing-server` (default implementation uses HTTP).

```python
from api.ch_query import CHQueryEngineFactory

# Connect to local server (default port 8080)
factory = CHQueryEngineFactory(server_url="http://localhost:8080")
```

### 2. Register a Dataset

While the server handles the actual data loading, you registers the dataset name in the client factory to facilitate engine creation.

```python
# Create an engine for a specific dataset
# Note: The dataset must be loaded/configured on the server side
dataset_name = "Burnaby"
factory.register_dataset(dataset_name)

engine = factory.get_engine(dataset_name)
```

### 3. Compute a Route

Use `compute_route_latlon` to find the shortest path between two coordinates. The server handles:
1.  **Map Matching**: Finding the nearest road edges to your coordinates.
2.  **Pathfinding**: Running the bidirectional Dijkstra algorithm.
3.  **Geometry**: Returning the full path geometry.

```python
result = engine.compute_route_latlon(
    start_lat=49.2827, start_lng=-122.9781,
    end_lat=49.2500, end_lng=-122.9500
)

if result.success:
    print(f"Distance: {result.distance:.1f} meters")
    print(f"Path: {len(result.path)} edges")
    # result.geojson contains the full LineString geometry
else:
    print(f"Error: {result.error}")
```


### 4. Find Nearest Edges

You can query just for the nearest road edge(s).

**Single Nearest Edge:**
```python
result = engine.find_nearest_edge(lat=49.25, lon=-122.95)
if result['success']:
    print(f"Nearest Edge: {result['edge_id']} ({result['distance_meters']:.1f}m away)")
```

**Multiple Candidates (KNN):**
```python
# Find top 5 edges within 500 meters
result = engine.find_nearest_edges(
    lat=49.25, lon=-122.95,
    radius=500.0, max_candidates=5
)
if result['success']:
    for edge in result['edges']:
        print(f"Edge {edge['id']}: {edge['distance']:.1f}m")
```

## 📚 API Reference

### `CHQueryEngineFactory`

*   `__init__(server_url: str = "http://localhost:8080")`
    *   Initialize the factory pointing to the C++ server.
    
*   `register_dataset(name: str)`
    *   Register a known dataset name.
    
*   `get_engine(name: str) -> CHQueryEngine`
    *   Get a reusable engine instance for the specified dataset. Engines are cached for performance.

*   `check_health() -> dict`
    *   Check server status and get list of loaded datasets.
    *   **Returns**: `{"status": "healthy", "datasets_loaded": [...]}`

### `CHQueryEngine`

*   `compute_route_latlon(start_lat, start_lng, end_lat, end_lng) -> QueryResult`
    *   Computes the shortest path.
    *   **Returns**: `QueryResult` object.

### `QueryResult`

Data class containing the routing response.

*   `success` (bool): True if route was found.
*   `distance` (float): Total route length in meters.
*   `path` (List[int]): List of Edge IDs in the path.
*   `geojson` (dict): GeoJSON Feature object containing the route geometry (`LineString`).
*   `error` (str): Error message if `success` is False.
*   `runtime_ms` (float): Server-side processing time (optional).
