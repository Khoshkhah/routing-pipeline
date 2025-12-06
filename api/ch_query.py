"""
Python SDK for Contraction Hierarchy Query Engine.

This module provides a clean interface to the C++ Contraction Hierarchy
query engine, supporting both single queries and efficient multi-source
multi-target batch queries.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    """Result from a shortest path query."""
    success: bool
    distance: Optional[float] = None
    runtime_ms: Optional[float] = None
    path: Optional[List[int]] = None
    error: Optional[str] = None


class CHQueryEngine:
    """
    Contraction Hierarchy query engine wrapper.
    
    Provides efficient shortest path queries using precomputed
    Contraction Hierarchies.
    
    Example:
        >>> engine = CHQueryEngine(
        ...     shortcuts_path="data/shortcuts.parquet",
        ...     edges_path="data/edges.csv",
        ...     binary_path="build/shortcut_router"
        ... )
        >>> result = engine.query(source=1234, target=5678)
        >>> if result.success:
        ...     print(f"Distance: {result.distance}m")
        ...     print(f"Path: {result.path}")
    """
    
    def __init__(
        self,
        shortcuts_path: str,
        edges_path: str,
        binary_path: str,
        timeout: int = 30
    ):
        """
        Initialize the query engine.
        
        Args:
            shortcuts_path: Path to shortcuts parquet file/directory
            edges_path: Path to edges CSV file with H3 metadata
            binary_path: Path to C++ query binary
            timeout: Query timeout in seconds (default: 30)
        
        Raises:
            FileNotFoundError: If binary doesn't exist
        """
        self.shortcuts_path = str(Path(shortcuts_path).resolve())
        self.edges_path = str(Path(edges_path).resolve())
        self.binary_path = Path(binary_path).resolve()
        self.timeout = timeout
        self._supports_multi_query = None  # Cache for binary capabilities
        
        if not self.binary_path.exists():
            raise FileNotFoundError(f"Query binary not found: {self.binary_path}")
    
    def _check_multi_query_support(self) -> bool:
        """Check if binary supports multi-query arguments."""
        if self._supports_multi_query is not None:
            return self._supports_multi_query
        
        try:
            # Run binary with --help to check available options
            result = subprocess.run(
                [str(self.binary_path), "--help"],
                capture_output=True,
                text=True,
                timeout=5
            )
            # Check if new multi-query arguments are supported
            output = result.stdout + result.stderr
            self._supports_multi_query = "--sources" in output and "--optimized" in output
            return self._supports_multi_query
        except Exception:
            # If we can't determine, assume old binary
            self._supports_multi_query = False
            return False
    
    def query(
        self,
        source: int,
        target: int
    ) -> QueryResult:
        """
        Find shortest path between two edges.
        
        Args:
            source: Source edge ID
            target: Target edge ID
        
        Returns:
            QueryResult with path and distance
        """
        cmd = [
            str(self.binary_path),
            "--shortcuts", self.shortcuts_path,
            "--edges", self.edges_path,
            "--source", str(source),
            "--target", str(target)
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            if result.returncode != 0:
                return QueryResult(
                    success=False,
                    error="No path found or query failed"
                )
            
            return self._parse_output(result.stdout)
        
        except subprocess.TimeoutExpired:
            return QueryResult(
                success=False,
                error=f"Query timeout after {self.timeout}s"
            )
        except Exception as e:
            return QueryResult(
                success=False,
                error=f"Query error: {e}"
            )
    
    def query_multi(
        self,
        source_edges: List[int],
        target_edges: List[int],
        source_distances: List[float],
        target_distances: List[float],
        optimized: bool = True
    ) -> QueryResult:
        """
        Find shortest path from any source edge to any target edge.
        
        This is more efficient than running len(source_edges) × len(target_edges)
        separate queries.
        
        Args:
            source_edges: List of source edge IDs
            target_edges: List of target edge IDs
            source_distances: Distance from origin to each source edge
            target_distances: Distance from each target edge to destination
            optimized: Use O(E log V) optimized algorithm (default: True)
                      If False, uses O(N*M*E log V) batch processing
        
        Returns:
            QueryResult with best path including approach distances
        
        Example:
            >>> result = engine.query_multi(
            ...     source_edges=[100, 101, 102],
            ...     target_edges=[200, 201],
            ...     source_distances=[10.5, 15.2, 20.1],
            ...     target_distances=[12.3, 18.7],
            ...     optimized=True
            ... )
            >>> # Tests 3×2=6 combinations efficiently in O(E log V)
        """
        if len(source_edges) != len(source_distances):
            return QueryResult(
                success=False,
                error="source_edges and source_distances must have same length"
            )
        
        if len(target_edges) != len(target_distances):
            return QueryResult(
                success=False,
                error="target_edges and target_distances must have same length"
            )
        
        # Check if binary supports multi-query
        if not self._check_multi_query_support():
            # Fall back to individual queries for old binaries
            return self._query_multi_fallback(source_edges, target_edges, source_distances, target_distances)
        
        cmd = [
            str(self.binary_path),
            "--shortcuts", self.shortcuts_path,
            "--edges", self.edges_path,
            "--sources", ",".join(map(str, source_edges)),
            "--source-dists", ",".join(map(str, source_distances)),
            "--targets", ",".join(map(str, target_edges)),
            "--target-dists", ",".join(map(str, target_distances))
        ]
        
        if optimized:
            cmd.append("--optimized")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            if result.returncode != 0:
                return QueryResult(
                    success=False,
                    error="No path found between source and target sets"
                )
            
            return self._parse_output(result.stdout)
        
        except subprocess.TimeoutExpired:
            return QueryResult(
                success=False,
                error=f"Query timeout after {self.timeout}s"
            )
        except Exception as e:
            return QueryResult(
                success=False,
                error=f"Query error: {e}"
            )
    
    def _query_multi_fallback(
        self,
        source_edges: List[int],
        target_edges: List[int],
        source_distances: List[float],
        target_distances: List[float]
    ) -> QueryResult:
        """
        Fallback implementation for old binaries without multi-query support.
        Tests all source×target combinations using individual queries.
        """
        best_distance = float('inf')
        best_path = None
        best_runtime = 0
        
        for i, source_edge in enumerate(source_edges):
            for j, target_edge in enumerate(target_edges):
                result = self.query(source_edge, target_edge)
                
                if result.success and result.distance is not None:
                    # Add approach distances
                    total_distance = source_distances[i] + result.distance + target_distances[j]
                    
                    if total_distance < best_distance:
                        best_distance = total_distance
                        best_path = result.path
                        best_runtime = result.runtime_ms
        
        if best_path is None:
            return QueryResult(
                success=False,
                error="No path found between source and target sets"
            )
        
        return QueryResult(
            success=True,
            distance=best_distance,
            runtime_ms=best_runtime,
            path=best_path
        )
    
    def _parse_output(self, output: str) -> QueryResult:
        """
        Parse C++ binary output.
        
        Handles both single query and multi-query formats:
        - Single: "Distance (including destination edge): X"
        - Multi: "Distance (total including approach distances): X"
        
        Args:
            output: C++ binary stdout
        
        Returns:
            QueryResult parsed from output
        """
        try:
            # Debug: Print raw output
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Raw C++ output:\n{output}")
            
            lines = output.strip().split('\n')
            
            distance = None
            runtime_ms = None
            path = None
            
            for line in lines:
                line = line.strip()
                
                if "No path found" in line:
                    return QueryResult(
                        success=False,
                        error="No path found"
                    )
                
                # Handle both output formats
                if "Distance" in line and ("including destination edge" in line or 
                                          "total including" in line):
                    distance = float(line.split(':')[1].strip())
                
                elif "Runtime:" in line:
                    runtime_str = line.split(':')[1].strip().replace('ms', '').strip()
                    runtime_ms = float(runtime_str)
                
                elif "Expanded path:" in line or "Expanded base edge path:" in line:
                    # Extract path: "1593 -> 34486 -> 24508 -> 4835"
                    path_str = line.split(':')[1].strip()
                    # Remove ellipsis if present
                    path_str = path_str.replace('...', '')
                    path_parts = [p.strip() for p in path_str.split('->')]
                    path = [int(p) for p in path_parts if p and p.isdigit()]
            
            if path is None or distance is None:
                return QueryResult(
                    success=False,
                    error="Failed to parse query output"
                )
            
            return QueryResult(
                success=True,
                distance=distance,
                runtime_ms=runtime_ms,
                path=path
            )
        
        except Exception as e:
            logger.error(f"Error parsing output: {e}")
            return QueryResult(
                success=False,
                error=f"Parse error: {e}"
            )


class CHQueryEngineFactory:
    """
    Factory for creating CHQueryEngine instances from configuration.
    
    Example:
        >>> factory = CHQueryEngineFactory()
        >>> factory.register_dataset(
        ...     name="Burnaby",
        ...     shortcuts_path="data/shortcuts.parquet",
        ...     edges_path="data/edges.csv",
        ...     binary_path="build/shortcut_router"
        ... )
        >>> engine = factory.get_engine("Burnaby")
        >>> result = engine.query(source=100, target=200)
    """
    
    def __init__(self):
        self._engines = {}
        self._configs = {}
    
    def register_dataset(
        self,
        name: str,
        shortcuts_path: str,
        edges_path: str,
        binary_path: str,
        timeout: int = 30
    ):
        """
        Register a dataset configuration.
        
        Args:
            name: Dataset identifier
            shortcuts_path: Path to shortcuts parquet
            edges_path: Path to edges CSV
            binary_path: Path to query binary
            timeout: Query timeout in seconds
        """
        self._configs[name] = {
            'shortcuts_path': shortcuts_path,
            'edges_path': edges_path,
            'binary_path': binary_path,
            'timeout': timeout
        }
    
    def get_engine(self, name: str) -> CHQueryEngine:
        """
        Get or create a query engine for a dataset.
        
        Engines are cached for reuse.
        
        Args:
            name: Dataset identifier
        
        Returns:
            CHQueryEngine instance
        
        Raises:
            KeyError: If dataset not registered
        """
        if name not in self._configs:
            raise KeyError(f"Dataset not registered: {name}")
        
        if name not in self._engines:
            config = self._configs[name]
            self._engines[name] = CHQueryEngine(**config)
        
        return self._engines[name]
    
    def list_datasets(self) -> List[str]:
        """Get list of registered dataset names."""
        return list(self._configs.keys())
