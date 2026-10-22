#!/bin/bash

# Build script for the common utils Lambda layer.
#
# requests itself is pure Python, but its transitive dependency charset_normalizer
# ships a compiled extension. Plain `pip install` on macOS/ARM64 compiles that
# extension for Darwin/ARM64, which is incompatible with the Lambda runtime
# (Amazon Linux x86_64) - the same class of bug google_genai's layer hit.
# --platform/--only-binary forces pip to download the manylinux x86_64 wheel
# instead of building locally, so this script works cross-platform without Docker.

set -e

echo "Building common utils Lambda layer..."

# Clean previous build
rm -rf build/
rm -f utils_layer.zip

# Create build directory
mkdir -p build
cp -r python build/

cd build

echo "Installing dependencies..."
pip install -r ../requirements.txt --target python/ --upgrade \
    --platform manylinux2014_x86_64 --only-binary=:all: \
    --python-version 3.9 --implementation cp

echo "Creating layer zip file..."
zip -r ../utils_layer.zip python/ -x "*/__pycache__/*"

cd ..

# Clean up build directory
rm -rf build/

echo "✅ Common utils layer built successfully: utils_layer.zip"
echo "📁 Size: $(du -h utils_layer.zip | cut -f1)"
echo ""
echo "📋 Next steps:"
echo "   1. Upload utils_layer.zip to S3"
echo "   2. Run terraform apply to update the layer"
