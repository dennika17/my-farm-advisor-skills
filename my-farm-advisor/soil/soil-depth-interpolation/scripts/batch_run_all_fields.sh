#!/bin/bash
set -u

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
SKILL_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
PYTHON_SCRIPT="$SKILL_DIR/src/soil_depth_interpolation.py"
PYTHON="/home/coder/my-farm-advisor-runtime/data-pipeline/.venv/bin/python"
DATA_ROOT="/home/coder/my-farm-advisor-runtime/data-pipeline"
FAILED_LOG="$SKILL_DIR/failed_fields_$(date +%Y%m%d_%H%M%S).log"

PASS_COUNT=0
FAIL_COUNT=0

process_farm() {
    local grower=$1
    local farm=$2
    local boundary="$DATA_ROOT/growers/$grower/farms/$farm/boundary/field_boundaries.geojson"
    local fields_dir="$DATA_ROOT/growers/$grower/farms/$farm/fields"
    
    echo "========================================"
    echo "=== Processing $farm ($grower) ==="
    echo "========================================"
    
    for field_dir in "$fields_dir"/*/; do
        local field_slug=$(basename "$field_dir")
        local output_dir="$field_dir/soil"
        
        echo ""
        echo "[$PASS_COUNT passed, $FAIL_COUNT failed] Processing $field_slug..."
        
        if "$PYTHON" "$PYTHON_SCRIPT" \
            --field-geojson "$boundary" \
            --output-dir "$output_dir" \
            --field-id "$field_slug" \
            --sda-timeout 300; then
            PASS_COUNT=$((PASS_COUNT + 1))
            echo "✓ $field_slug SUCCESS"
        else
            FAIL_COUNT=$((FAIL_COUNT + 1))
            echo "✗ $field_slug FAILED"
            echo "$grower/$farm/$field_slug" >> "$FAILED_LOG"
        fi
    done
}

# Nebraska (10 fields)
process_farm "nebraska-grower" "nebraska-farm"

# Illinois (9 remaining fields + 1 already done)
process_farm "northern-illinois-grower" "illinois-farm"

# Iowa (10 fields)
process_farm "northern-iowa-grower" "iowa-farm"

echo ""
echo "========================================"
echo "FINAL SUMMARY"
echo "========================================"
echo "Passed: $PASS_COUNT"
echo "Failed: $FAIL_COUNT"
echo "Total:  $((PASS_COUNT + FAIL_COUNT))"
if [ -f "$FAILED_LOG" ]; then
    echo "Failed fields: $FAILED_LOG"
fi
echo "========================================"
