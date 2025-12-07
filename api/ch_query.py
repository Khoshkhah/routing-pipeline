import requests
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
import logging
import json

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    """Result from a shortest path query."""
    success: bool
    distance: Optional[float] = None
    runtime_ms: Optional[float] = None
    path: Optional[List[int]] = None
    geojson: Optional[dict] = None  # Add GeoJSON support
    error: Optional[str] = None


class CHQueryEngine:
    # ... (init and loaded check remain same)

    def __init__(
        self,
        dataset_name: str,
        server_url: str = "http://localhost:8080",
        timeout: int = 30
    ):
        """
        Initialize the query engine client.
        
        Args:
            dataset_name: Name of the dataset to query (e.g. "Burnaby")
            server_url: Base URL of the routing server
            timeout: Request timeout in seconds
        """
        self.dataset_name = dataset_name.lower()
        self.server_url = server_url.rstrip('/')
        self.timeout = timeout
        
        self._ensure_dataset_loaded()
    
    def _ensure_dataset_loaded(self):
        try:
            payload = {"dataset": self.dataset_name}
            # Just try to load - idempotent
            requests.post(
                f"{self.server_url}/load_dataset",
                json=payload,
                timeout=self.timeout
            )
        except Exception as e:
            logger.error(f"Failed to communicate with routing server: {e}")

    def query(self, source: int, target: int) -> QueryResult:
        return QueryResult(False, error="Raw edge query not supported by HTTP client yet. Use compute_route_latlon.")
    
    def query_multi(self, *args, **kwargs) -> QueryResult:
        return QueryResult(False, error="Raw edge query not supported by HTTP client yet. Use compute_route_latlon.")

    def compute_route_latlon(
        self,
        start_lat: float,
        start_lng: float,
        end_lat: float,
        end_lng: float
    ) -> QueryResult:
        """
        Compute route using the routing server's full stack (NN + CH).
        """
        try:
            payload = {
                "dataset": self.dataset_name,
                "start_lat": start_lat,
                "start_lng": start_lng,
                "end_lat": end_lat,
                "end_lng": end_lng
            }
            response = requests.post(
                f"{self.server_url}/route",
                json=payload,
                timeout=self.timeout
            )
            data = response.json()
            # logger.info(f"DEBUG: Raw response from server: {data}")
            
            if not data.get("success", False):
                return QueryResult(success=False, error=data.get("error", "Unknown server error"))
            
            route_container = data.get("route", {})
            # logger.info(f"DEBUG: Route Container: {route_container}")
            
            # The server wraps the engine result which wraps the route details
            # Structure: {success:true, route: {dataset:..., route: {distance:..., geojson:...}}}
            route_details = route_container.get("route", {})
            
            return QueryResult(
                success=True,
                distance=route_details.get("distance"),
                path=route_details.get("path"),
                geojson=route_details.get("geojson")
            )
        except Exception as e:
            logger.error(f"Routing request failed: {e}")
            return QueryResult(success=False, error=str(e))

    def find_nearest_edges(self, lat: float, lon: float, radius: float = 1000.0, max_candidates: int = 5) -> dict:
        """
        Find multiple nearest edges to the given coordinates.
        
        Args:
            lat: Latitude
            lon: Longitude
            radius: Search radius in meters
            max_candidates: Maximum number of edges to return
            
        Returns:
            Dict with keys: success, edges (list of {id, distance}), error
        """
        try:
            payload = {
                "dataset": self.dataset_name,
                "lat": lat,
                "lon": lon,
                "radius": radius,
                "max_candidates": max_candidates
            }
            response = requests.post(
                f"{self.server_url}/nearest_edges",
                json=payload,
                timeout=self.timeout
            )
            return response.json()
        except Exception as e:
            logger.error(f"Nearest edges request failed: {e}")
            return {"success": False, "error": str(e)}

    def find_nearest_edge(self, lat: float, lon: float) -> dict:
        """
        Find the nearest edge to the given coordinates.
        
        Args:
            lat: Latitude
            lon: Longitude
            
        Returns:
            Dict with keys: success, edge_id, distance_meters, runtime_ms, error
        """
        try:
            payload = {
                "dataset": self.dataset_name,
                "lat": lat,
                "lon": lon
            }
            response = requests.post(
                f"{self.server_url}/nearest_edge",
                json=payload,
                timeout=self.timeout
            )
            return response.json()
        except Exception as e:
            logger.error(f"Nearest edge request failed: {e}")
            return {"success": False, "error": str(e)}


class CHQueryEngineFactory:
    """
    Factory that now produces HTTP clients.
    """
    
    def __init__(self, server_url: str = "http://localhost:8080"):
        self.server_url = server_url
        self._configs = {}
        self._engines = {}  # Cache for instantiated engines
    
    def register_dataset(self, name: str, **kwargs):
        """
        Register dataset.
        
        Args:
           name: Dataset name (e.g. "Burnaby")
           **kwargs: Ignored for HTTP client (paths are handled by server)
        """
        self._configs[name] = kwargs
        # Invalidate cache if re-registering? 
        # For now, simplistic overwrite.
        if name in self._engines:
            del self._engines[name]
    
    def get_engine(self, name: str) -> CHQueryEngine:
        # Check cache first
        if name not in self._engines:
            self._engines[name] = CHQueryEngine(name, self.server_url)
        return self._engines[name]
    
    def check_health(self) -> dict:
        """
        Check if the routing server is healthy and get loaded datasets.
        
        Returns:
            Dict with keys: status, datasets_loaded
        """
        try:
            response = requests.get(f"{self.server_url}/health", timeout=5)
            return response.json()
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    def list_datasets(self) -> List[str]:
        return list(self._configs.keys())
