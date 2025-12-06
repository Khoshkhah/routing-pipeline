"""
FastAPI server for the Contraction Hierarchies routing application.

This server provides REST API endpoints for:
- Listing available datasets
- Finding nearest edges to coordinates
- Computing shortest paths and returning GeoJSON routes
"""

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from api.data_loader import DatasetRegistry
from api.ch_query import CHQueryEngineFactory

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Contraction Hierarchies Routing API",
    description="REST API for querying shortest paths on road networks using Contraction Hierarchies",
    version="1.0.0"
)

# Enable CORS for Streamlit frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global dataset registry
registry = DatasetRegistry()

# Global CH query engine factory
ch_factory = CHQueryEngineFactory()


class DatasetInfo(BaseModel):
    """Dataset metadata."""
    name: str
    shortcuts_path: str
    edges_path: str
    binary_path: str
    bounds: Optional[List[float]] = None
    center: Optional[List[float]] = None


class NearestEdgeResponse(BaseModel):
    """Response for nearest edge query."""
    edge_id: int
    distance: float
    lat: float
    lon: float


class RouteResponse(BaseModel):
    """Response for route query."""
    success: bool
    distance: Optional[float] = None
    runtime_ms: Optional[float] = None
    path: Optional[List[int]] = None
    geojson: Optional[Dict] = None
    error: Optional[str] = None


def load_config(config_path: str = "config/datasets.yaml"):
    """Load dataset configuration from YAML file."""
    config_file = Path(config_path)
    
    if not config_file.exists():
        logger.warning(f"Config file not found: {config_path}")
        return
    
    logger.info(f"Loading configuration from {config_path}")
    
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)
    
    datasets = config.get('datasets', [])
    base_dir = config_file.parent.parent
    
    for ds in datasets:
        name = ds['name']
        shortcuts_path = ds['shortcuts_path']
        edges_path = ds['edges_path']
        binary_path = ds['binary_path']
        
        # Resolve relative paths
        if not Path(shortcuts_path).is_absolute():
            shortcuts_path = str(base_dir / shortcuts_path)
        if not Path(edges_path).is_absolute():
            edges_path = str(base_dir / edges_path)
        if not Path(binary_path).is_absolute():
            binary_path = str(base_dir / binary_path)
        
        registry.register_dataset(name, shortcuts_path, edges_path, binary_path)
        logger.info(f"Registered dataset '{name}'")
        
        # Also register with CH query engine factory
        try:
            ch_factory.register_dataset(
                name=name,
                shortcuts_path=shortcuts_path,
                edges_path=edges_path,
                binary_path=binary_path,
                timeout=30
            )
        except FileNotFoundError as e:
            logger.warning(f"CH engine not available for {name}: {e}")


@app.on_event("startup")
async def startup_event():
    """Load configuration on startup."""
    logger.info("Starting Contraction Hierarchies API server...")
    load_config()
    logger.info("Server startup complete")


@app.get("/")
async def root():
    """API root endpoint."""
    return {
        "name": "Contraction Hierarchies Routing API",
        "version": "1.0.0",
        "endpoints": {
            "/datasets": "List available datasets",
            "/nearest-edge": "Find nearest edge to coordinates",
            "/route": "Compute shortest path between two points"
        }
    }


@app.get("/datasets", response_model=List[DatasetInfo])
async def list_datasets():
    """List all available datasets."""
    dataset_names = registry.list_datasets()
    
    result = []
    for name in dataset_names:
        info = registry.get_dataset_info(name)
        
        # Get spatial bounds (lazy load)
        try:
            spatial_idx = registry.get_spatial_index(name)
            bounds = spatial_idx.get_bounds()
            bounds_list = [bounds[0], bounds[1], bounds[2], bounds[3]]  # [minx, miny, maxx, maxy]
            center = [(bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2]
        except Exception as e:
            logger.warning(f"Failed to get bounds for {name}: {e}")
            bounds_list = None
            center = None
        
        result.append(DatasetInfo(
            name=name,
            shortcuts_path=info['shortcuts_path'],
            edges_path=info['edges_path'],
            binary_path=info['binary_path'],
            bounds=bounds_list,
            center=center
        ))
    
    return result


@app.get("/nearest-edge", response_model=NearestEdgeResponse)
async def find_nearest_edge(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    dataset: str = Query(..., description="Dataset name")
):
    """Find the nearest edge to given coordinates."""
    if dataset not in registry.list_datasets():
        raise HTTPException(status_code=404, detail=f"Dataset not found: {dataset}")
    
    try:
        spatial_idx = registry.get_spatial_index(dataset)
        result = spatial_idx.find_nearest_edge(lat, lon)
        
        if result is None:
            raise HTTPException(status_code=404, detail="No nearby edges found")
        
        edge_id, distance = result
        
        return NearestEdgeResponse(
            edge_id=edge_id,
            distance=distance,
            lat=lat,
            lon=lon
        )
    
    except Exception as e:
        logger.error(f"Error finding nearest edge: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/route", response_model=RouteResponse)
async def compute_route(
    source_lat: float = Query(..., description="Source latitude"),
    source_lon: float = Query(..., description="Source longitude"),
    target_lat: float = Query(..., description="Target latitude"),
    target_lon: float = Query(..., description="Target longitude"),
    dataset: str = Query(..., description="Dataset name"),
    search_mode: str = Query("knn", description="Search mode: 'knn' for k-nearest neighbors or 'radius' for radius search"),
    num_candidates: int = Query(3, description="Number of candidate edges (for knn mode)", ge=1, le=10),
    search_radius: float = Query(100.0, description="Search radius in meters (for radius mode)", ge=10.0, le=500.0)
):
    """Compute shortest path between two points using candidate edge search."""
    if dataset not in registry.list_datasets():
        raise HTTPException(status_code=404, detail=f"Dataset not found: {dataset}")
    
    if search_mode not in ['knn', 'radius']:
        raise HTTPException(status_code=400, detail="search_mode must be 'knn' or 'radius'")
    
    try:
        # Find candidate edges for source and target
        spatial_idx = registry.get_spatial_index(dataset)
        
        if search_mode == 'knn':
            # k-nearest neighbors approach
            source_candidates = spatial_idx.find_nearest_edges(source_lat, source_lon, max_results=num_candidates)
            target_candidates = spatial_idx.find_nearest_edges(target_lat, target_lon, max_results=num_candidates)
            search_desc = f"{num_candidates}-nearest neighbors"
        else:
            # Radius-based search
            source_candidates = spatial_idx.find_edges_within_radius(source_lat, source_lon, search_radius, max_results=num_candidates)
            target_candidates = spatial_idx.find_edges_within_radius(target_lat, target_lon, search_radius, max_results=num_candidates)
            search_desc = f"{search_radius}m radius"
        
        if not source_candidates:
            return RouteResponse(success=False, error=f"No edge found near source point using {search_desc}. Try adjusting search parameters or clicking closer to a road.")
        
        if not target_candidates:
            return RouteResponse(success=False, error=f"No edge found near target point using {search_desc}. Try adjusting search parameters or clicking closer to a road.")
        
        logger.info(f"Testing {len(source_candidates)} source × {len(target_candidates)} target candidates ({search_mode} mode)")
        
        # Get CH query engine
        try:
            ch_engine = ch_factory.get_engine(dataset)
        except KeyError:
            return RouteResponse(success=False, error=f"Query engine not available for dataset: {dataset}")
        
        # Use efficient batch query with multi-source multi-target
        source_edges = [edge_id for edge_id, _ in source_candidates]
        source_dists = [dist for _, dist in source_candidates]
        target_edges = [edge_id for edge_id, _ in target_candidates]
        target_dists = [dist for _, dist in target_candidates]
        
        # Run multi-query using SDK
        result = ch_engine.query_multi(
            source_edges=source_edges,
            target_edges=target_edges,
            source_distances=source_dists,
            target_distances=target_dists
        )
        
        if not result.success:
            logger.warning(f"Query failed: {result.error}")
            return RouteResponse(success=False, error=result.error)
        
        logger.info(f"Best path found with total distance: {result.distance:.2f}m")
        
        # Build GeoJSON from path
        spatial_idx = registry.get_spatial_index(dataset)
        geojson = build_geojson(result.path, spatial_idx)
        
        return RouteResponse(
            success=True,
            distance=result.distance,
            runtime_ms=result.runtime_ms,
            path=result.path,
            geojson=geojson
        )
    
    except Exception as e:
        logger.error(f"Error computing route: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def parse_cpp_output(output: str) -> tuple:
    """
    Parse C++ binary output.
    
    Expected format:
        Query 1593 -> 4835
          Distance (including destination edge): 433.75
          Destination edge cost: 267.604
          Shortcut path length: 5 edges
          Shortcut path: 1593 -> 34486 -> 24508 -> 8504 -> 4835
          Expanded base edge path length: 6 edges
          Expanded base edge path: 1593 -> ... -> 4835
          Runtime: 0.42 ms
    
    Returns:
        (path, distance, runtime_ms) or (None, None, None) if parsing fails
    """
    try:
        lines = output.strip().split('\n')
        
        distance = None
        runtime_ms = None
        path = None
        
        for line in lines:
            line = line.strip()
            
            if "No path found" in line:
                return None, None, None
            
            # Handle both single query and multi-query output formats
            if "Distance" in line and ("including destination edge" in line or "total including" in line):
                distance = float(line.split(':')[1].strip())
            
            elif "Runtime:" in line:
                runtime_str = line.split(':')[1].strip().replace('ms', '').strip()
                runtime_ms = float(runtime_str)
            
            elif "Expanded path:" in line or "Expanded base edge path:" in line:
                # Extract path: "1593 -> 34486 -> 24508 -> 4835"
                path_str = line.split(':')[1].strip()
                # Handle both full paths and truncated paths with "..."
                path_str = path_str.replace('...', '')
                path_parts = [p.strip() for p in path_str.split('->')]
                path = [int(p) for p in path_parts if p and p.isdigit()]
        
        if path is None:
            logger.warning("Failed to parse path from C++ output")
            return None, None, None
        
        return path, distance, runtime_ms
    
    except Exception as e:
        logger.error(f"Error parsing C++ output: {e}")
        return None, None, None


def build_geojson(path: List[int], spatial_idx) -> Dict:
    """
    Build GeoJSON LineString from edge path.
    
    Args:
        path: List of edge IDs
        spatial_idx: SpatialIndex instance
    
    Returns:
        GeoJSON FeatureCollection
    """
    features = []
    
    for edge_id in path:
        edge_data = spatial_idx.get_edge(edge_id)
        
        if edge_data is None:
            logger.warning(f"Edge {edge_id} not found in spatial index")
            continue
        
        coords = list(edge_data.geometry.coords)
        
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": coords
            },
            "properties": {
                "edge_id": edge_id,
                "length": edge_data.length,
                "highway": edge_data.highway
            }
        }
        features.append(feature)
    
    return {
        "type": "FeatureCollection",
        "features": features
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
