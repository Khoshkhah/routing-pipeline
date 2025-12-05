# Hierarchical Routing Pipeline

A complete end-to-end pipeline for building and querying Contraction Hierarchies on OpenStreetMap road networks with H3 geospatial indexing.

## 🎯 Overview

This pipeline transforms raw OpenStreetMap data into a production-ready shortest-path query system. It consists of three specialized repositories that work together:

```
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│ osm-to-road-network │────▶│ spark-shortest-path │────▶│dijkstra-on-Hierarchy│
│                     │     │                     │     │                     │
│  • OSM PBF parsing  │     │  • PySpark CH build │     │  • C++ query engine │
│  • H3 indexing      │     │  • Hierarchy-aware  │     │  • Bidirectional    │
│  • Turn restrictions│     │    shortest paths   │     │    Dijkstra         │
│  • Speed inference  │     │  • Parquet output   │     │  • Sub-ms latency   │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
        Stage 1                    Stage 2                    Stage 3
       EXTRACT                   PREPROCESS                   QUERY
```

## 📦 Repositories

| Stage | Repository | Description | Language |
|-------|------------|-------------|----------|
| 1 | [osm-to-road-network](https://github.com/khoshkhah/osm-to-road-network) | Converts OSM data to road network with H3 indexing | Python |
| 2 | [spark-shortest-path](https://github.com/khoshkhah/spark-shortest-path) | Builds Contraction Hierarchy shortcuts at scale | PySpark |
| 3 | [dijkstra-on-Hierarchy](https://github.com/khoshkhah/dijkstra-on-Hierarchy) | Production C++ query engine | C++20 |

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- Apache Spark 3.x (for Stage 2)
- C++20 compiler, CMake, Arrow/Parquet, libh3 (for Stage 3)

### Step 1: Extract Road Network

```bash
git clone https://github.com/khoshkhah/osm-to-road-network.git
cd osm-to-road-network
pip install -r requirements.txt

python scripts/create_network.py --region Kentucky --district Somerset --output data/output
```

**Output:**
- `Somerset_driving_simplified_edges_with_h3.csv` - Road edges with H3 cells
- `Somerset_driving_edge_graph.csv` - Edge connectivity (turn-aware)

### Step 2: Build Contraction Hierarchy

```bash
git clone https://github.com/khoshkhah/spark-shortest-path.git
cd spark-shortest-path
pip install -r requirements.txt

python src/shortest_path_hybrid.py \
    --edges ../osm-to-road-network/data/output/Somerset_driving_simplified_edges_with_h3.csv \
    --graph ../osm-to-road-network/data/output/Somerset_driving_edge_graph.csv \
    --output output/shortcuts.parquet
```

**Output:**
- `shortcuts.parquet` - Contraction Hierarchy shortcuts with via_edge for expansion

### Step 3: Query Shortest Paths

```bash
git clone https://github.com/khoshkhah/dijkstra-on-Hierarchy.git
cd dijkstra-on-Hierarchy

# Build (requires conda environment or system packages)
./build_cpp.sh

# Query
./run_cpp.sh \
    --shortcuts ../spark-shortest-path/output/shortcuts.parquet \
    --edges ../osm-to-road-network/data/output/Somerset_driving_simplified_edges_with_h3.csv \
    --source 1593 --target 4835
```

**Output:**
```
Query: 1593 -> 4835
  Distance: 2847.32
  Path (shortcuts): [1593, 2041, 3892, 4835]
  Path (expanded):  [1593, 1594, 1601, 2041, 2042, 3890, 3891, 3892, 4835]
  Time: 0.42 ms
```

## 📊 Data Flow

```
OpenStreetMap PBF
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│                    osm-to-road-network                       │
│  • Parse OSM ways and nodes                                  │
│  • Build road graph with osmnx                               │
│  • Apply turn restrictions from OSM relations                │
│  • Assign H3 cells (resolution 15) to nodes                  │
│  • Compute LCA resolution for edge pairs                     │
│  • Calculate travel costs from length/speed                  │
└──────────────────────────────────────────────────────────────┘
       │
       │  edges_with_h3.csv, edge_graph.csv
       ▼
┌──────────────────────────────────────────────────────────────┐
│                    spark-shortest-path                       │
│  • Partition graph by H3 cells                               │
│  • Compute all-pairs shortest paths per partition            │
│  • Build shortcuts with via_edge for path expansion          │
│  • Assign hierarchy direction (inside: +1, 0, -1)            │
│  • Output as Parquet with H3 cell annotations                │
└──────────────────────────────────────────────────────────────┘
       │
       │  shortcuts.parquet
       ▼
┌──────────────────────────────────────────────────────────────┐
│                   dijkstra-on-Hierarchy                      │
│  • Load shortcuts via Apache Arrow (zero-copy)               │
│  • Build forward/backward adjacency lists                    │
│  • Hierarchy-aware bidirectional Dijkstra                    │
│  • Expand shortcuts to base edges via via_edge               │
│  • Sub-millisecond query latency                             │
└──────────────────────────────────────────────────────────────┘
       │
       ▼
   Query Results
   (distance, path, expanded_path)
```

## 🔑 Key Features

### H3 Geospatial Hierarchy
All three stages use Uber's H3 hexagonal indexing system:
- **Stage 1**: Assigns H3 cells to road network nodes
- **Stage 2**: Partitions computation by H3 cells for parallelism
- **Stage 3**: Uses H3 ancestry for hierarchy-aware search pruning

### Turn Restrictions
Unlike basic OSM converters, this pipeline explicitly handles turn restrictions:
- Parses OSM relations (`no_left_turn`, `no_u_turn`, etc.)
- Builds an edge-to-edge connectivity graph (dual graph)
- Routes never suggest illegal turns

### Contraction Hierarchy
The preprocessing stage builds a CH that enables:
- Forward search: only expands upward shortcuts (`inside == +1`)
- Backward search: only expands downward shortcuts (`inside == -1`)
- Meeting in the middle: optimal path reconstruction

### Path Expansion
Shortcuts can be recursively expanded to base edges:
- Each shortcut stores `via_edge` for intermediate edge
- Query engine unpacks `(u, v)` → `(u, via_edge) + (via_edge, v)`
- Returns both shortcut path and fully expanded base-edge path

## 📄 License

Each repository is independently licensed. See individual repositories for details.

## 🤝 Contributing

Contributions are welcome! Please submit issues and pull requests to the relevant repository.

## 👤 Author

[Kaveh Khoshkhah](https://github.com/khoshkhah)
