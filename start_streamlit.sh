#!/bin/bash
# Start the Streamlit web application

set -e

cd "$(dirname "$0")"

echo "Starting Streamlit web application..."
echo "Web app will be available at http://localhost:8501"
echo ""

streamlit run app/streamlit_app.py --server.port 8501 --server.address 0.0.0.0
