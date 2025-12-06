# Multi-stage Docker build for Contraction Hierarchies Web Application

# Stage 1: Build C++ query engine from dijkstra-on-Hierarchy
FROM condaforge/mambaforge:latest AS cpp-builder

RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Clone and build dijkstra-on-Hierarchy
RUN git clone https://github.com/khoshkhah/dijkstra-on-Hierarchy.git
WORKDIR /build/dijkstra-on-Hierarchy

# Create conda environment for C++ dependencies
RUN mamba create -n ch-query-engine \
    arrow-cpp \
    parquet-cpp \
    h3-c \
    -c conda-forge -y

# Build C++ binary
RUN bash -c "source activate ch-query-engine && ./build_cpp.sh"

# Stage 2: Python runtime with API and frontend
FROM python:3.10-slim

RUN apt-get update && apt-get install -y \
    libspatialindex-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy C++ binary from builder stage
COPY --from=cpp-builder /build/dijkstra-on-Hierarchy/build/shortcut_router /app/bin/shortcut_router

# Copy Python application code
COPY api ./api
COPY app ./app
COPY config ./config

# Install Python dependencies
RUN pip install --no-cache-dir -r api/requirements.txt
RUN pip install --no-cache-dir -r app/requirements.txt

# Create startup script
RUN echo '#!/bin/bash\n\
if [ "$1" = "api" ]; then\n\
    cd /app && python -m uvicorn api.server:app --host 0.0.0.0 --port 8000\n\
elif [ "$1" = "streamlit" ]; then\n\
    cd /app && streamlit run app/streamlit_app.py --server.port 8501 --server.address 0.0.0.0\n\
else\n\
    echo "Usage: docker run <image> [api|streamlit]"\n\
    exit 1\n\
fi' > /app/entrypoint.sh && chmod +x /app/entrypoint.sh

EXPOSE 8000 8501

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["api"]
