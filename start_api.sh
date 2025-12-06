#!/bin/bash
# Start the API server

set -e

cd "$(dirname "$0")"

echo "Starting Contraction Hierarchies API server..."
echo "API will be available at http://localhost:8000"
echo "API documentation at http://localhost:8000/docs"
echo ""

python -m uvicorn api.server:app --host 0.0.0.0 --port 8000 --reload
