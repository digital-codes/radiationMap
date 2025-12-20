#!/usr/bin/env bash
set -euo pipefail
SCHEMA_FILE="data/radiation_relevant_schema.json"
DB="data/radiation.db"
TABLE="radiation_data"

command -v jq >/dev/null 2>&1 || { echo "This script requires 'jq' (https://stedolan.github.io/jq/)"; exit 2; }
command -v sqlite3 >/dev/null 2>&1 || { echo "This script requires 'sqlite3'"; exit 2; }

if [ ! -f "$SCHEMA_FILE" ]; then
  echo "Schema file not found: $SCHEMA_FILE"
  exit 3
fi

# build column definitions: map "number"->REAL, "timestamp"->TEXT, others->TEXT
cols=$(jq -r '[.[] | "\"\(.name|gsub("\""; "\"\""))\" " + (if .type=="number" then "REAL" elif .type=="timestamp" then "TEXT" else "TEXT" end)] | join(", ")' "$SCHEMA_FILE")

sql="CREATE TABLE IF NOT EXISTS \"$TABLE\" ($cols);"

echo "Creating database '$DB' with table '$TABLE'..., statement: $sql"

# create DB and table
echo "$sql" | sqlite3 "$DB"


# create simple indexes if those columns exist
has_col() {
  jq -e --arg name "$1" '[.[] | .name] | index($name) // empty' "$SCHEMA_FILE" >/dev/null 2>&1
}

if has_col "sensor_id"; then
  echo "CREATE INDEX IF NOT EXISTS idx_${TABLE}_sensor_id ON \"$TABLE\"(\"sensor_id\");" | sqlite3 "$DB"
fi
if has_col "timestamp"; then
  echo "CREATE INDEX IF NOT EXISTS idx_${TABLE}_timestamp ON \"$TABLE\"(\"timestamp\");" | sqlite3 "$DB"
fi


