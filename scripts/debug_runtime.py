
import sys
import os
import yaml
import requests
import logging

# Setup path
sys.path.append(os.path.abspath("."))
from api.ch_query import CHQueryEngine

# Config
DATASET = "Burnaby"
SERVER_URL = "http://localhost:8080"

def debug_runtime():
    # 1. Inspect datasets.yaml to get paths (just for consistency, though we wont use them to register if we assume server works)
    # Actually, we just want to hit the server using CHQueryEngine logic
    
    # 2. Instantiate Engine
    print(f"Connecting to {SERVER_URL} for dataset {DATASET}")
    engine = CHQueryEngine(DATASET, SERVER_URL)
    
    # 3. Call private load (it should be idempotent)
    print("Ensuring dataset loaded...")
    engine._ensure_dataset_loaded()
    
    # 4. Formulate Request payload manually to see raw output
    payload = {
        "dataset": "burnaby", # lower case as per logic
        "start_lat": 49.23,
        "start_lng": -122.97,
        "end_lat": 49.24,
        "end_lng": -122.95
    }
    
    print("Sending request for route...")
    try:
        resp = requests.post(f"{SERVER_URL}/route", json=payload, timeout=10)
        data = resp.json()
        print("--- RAW C++ RESPONSE ---")
        import json
        print(json.dumps(data, indent=2))
        print("------------------------")
        
        # 5. Check what CHQueryEngine would return
        # Create a dummy engine instance to access the method
        # We can't easily call compute_route_latlon and see interal vars, so we just trust the RAW response inspection
        # But we can try calling the fixed method
        
        result = engine.compute_route_latlon(49.23, -122.97, 49.24, -122.95)
        print(f"\nCHQueryEngine.compute_route_latlon Result:")
        print(f"Success: {result.success}")
        print(f"Distance: {result.distance}")
        print(f"Runtime MS: {result.runtime_ms}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_runtime()
