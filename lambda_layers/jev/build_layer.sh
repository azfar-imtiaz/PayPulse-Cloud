#!/bin/bash

# Build script for the Jev (TypeSafe AI) Lambda layer.
#
# NOTE: typesafe-sdk pulls in pydantic, which has a compiled pydantic_core extension -
# building on macOS/ARM64 with this script produces Lambda-incompatible binaries.
# Use build_layer_docker.sh instead for any real deployment; this script is kept only
# for quick local syntax/import checks on a Linux x86_64 build machine.

set -e

echo "Building Jev (TypeSafe AI) Lambda layer..."

# Clean previous build
rm -rf build/
rm -f jev_layer.zip

# Create build directory
mkdir -p build
cp -r python build/

cd build

echo "Installing typesafe-sdk..."
pip install -r ../requirements.txt --target python/ --upgrade

echo "Creating layer zip file..."
zip -r ../jev_layer.zip python/

cd ..

# Clean up build directory
rm -rf build/

echo "✅ Jev layer built successfully: jev_layer.zip"
echo "📁 Size: $(du -h jev_layer.zip | cut -f1)"
echo ""
echo "📋 Next steps:"
echo "   1. Run terraform apply to update the layer"
