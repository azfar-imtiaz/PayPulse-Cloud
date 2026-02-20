#!/bin/bash

# Script to upload vendor configurations to DynamoDB VendorConfig table
# Usage: ./upload_vendors.sh

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

TABLE_NAME="VendorConfig"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "========================================="
echo "Uploading vendor configs to DynamoDB"
echo "Table: $TABLE_NAME"
echo "========================================="
echo ""

# Counter for statistics
total=0
success=0
already_exists=0
failed=0

# Iterate over all JSON files in subdirectories
for config_file in "$SCRIPT_DIR"/*/*.json; do
  # Check if any JSON files exist
  if [ ! -f "$config_file" ]; then
    echo -e "${YELLOW}No JSON files found in $SCRIPT_DIR subdirectories${NC}"
    exit 1
  fi

  filename=$(basename "$config_file")
  vendor_id=$(echo "$filename" | sed 's/.json$//')

  total=$((total + 1))

  echo -n "Uploading $filename ... "

  # Run the put-item command with condition expression
  if aws dynamodb put-item \
    --table-name "$TABLE_NAME" \
    --item "file://$config_file" \
    --condition-expression "attribute_not_exists(vendor_id)" \
    --no-cli-pager \
    2>&1 | grep -q "ConditionalCheckFailedException"; then

    echo -e "${YELLOW}ALREADY EXISTS${NC}"
    already_exists=$((already_exists + 1))

  elif [ ${PIPESTATUS[0]} -eq 0 ]; then
    echo -e "${GREEN}SUCCESS${NC}"
    success=$((success + 1))
  else
    echo -e "${RED}FAILED${NC}"
    failed=$((failed + 1))
  fi
done

echo ""
echo "========================================="
echo "Upload Summary"
echo "========================================="
echo "Total files:      $total"
echo -e "${GREEN}Successful:       $success${NC}"
echo -e "${YELLOW}Already existed:  $already_exists${NC}"
echo -e "${RED}Failed:           $failed${NC}"
echo "========================================="

# Exit with error code if any failed
if [ $failed -gt 0 ]; then
  exit 1
fi