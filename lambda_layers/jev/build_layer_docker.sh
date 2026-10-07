#!/bin/bash

# Build script for the Jev (TypeSafe AI) Lambda layer using Docker.
# typesafe-sdk pulls in pydantic (compiled pydantic_core extension) - building on
# macOS/ARM64 produces binaries incompatible with Lambda's x86_64 runtime. This mirrors
# lambda_layers/google_genai/build_layer_docker.sh, which hits the same issue.

set -e

echo "Building Jev (TypeSafe AI) Lambda layer using Docker..."

# Clean previous build
rm -rf build/
rm -f jev_layer.zip

# Create build directory
mkdir -p build

# Create Dockerfile for building
cat << 'EOF' > build/Dockerfile
FROM --platform=linux/amd64 public.ecr.aws/lambda/python:3.12

# Install zip utility
RUN dnf install -y zip

# Copy requirements and source files
COPY requirements.txt /var/task/
COPY python/ /var/task/python/

# Install dependencies
RUN pip install -r requirements.txt -t /var/task/python/

# Create the zip file
WORKDIR /var/task
RUN zip -r jev_layer.zip python/

# Copy the zip file to a volume
CMD cp jev_layer.zip /output/
EOF

# Copy files to build directory
cp requirements.txt build/
cp -r python build/

# Build using Docker
echo "Building layer using AWS Lambda Python 3.12 runtime..."
docker build -t jev-builder build/

# Run container and extract the zip file
# --entrypoint "" overrides the base image's Lambda runtime interface client entrypoint,
# which otherwise conflicts with our CMD (fails with "entrypoint requires the handler
# name to be the first argument").
echo "Extracting layer zip file..."
docker run --rm --entrypoint "" -v "$(pwd):/output" jev-builder cp jev_layer.zip /output/

# Clean up
rm -rf build/

echo "✅ Jev layer built successfully: jev_layer.zip"
echo "📁 Size: $(du -h jev_layer.zip | cut -f1)"
echo ""
echo "🐳 Built using AWS Lambda Python 3.12 Docker runtime"
echo "📋 Next steps:"
echo "   1. Run terraform apply to update the layer"
