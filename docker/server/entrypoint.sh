#!/bin/bash
set -e

if [ -n "${GOOGLE_APPLICATION_CREDENTIALS_JSON}" ]; then
  GOOGLE_APPLICATION_CREDENTIALS_DIR="${HOME}/.config/gcloud/"
  mkdir -p "${GOOGLE_APPLICATION_CREDENTIALS_DIR}"
  echo "${GOOGLE_APPLICATION_CREDENTIALS_JSON}" > "${GOOGLE_APPLICATION_CREDENTIALS_DIR}/application_default_credentials.json"
fi

DB_PATH="${HOME}/.dstack/server/data/sqlite.db"
mkdir -p "$(dirname "$DB_PATH")"
if [[ -z "${LITESTREAM_REPLICA_URL}" ]]; then
  exec dstack server --host 0.0.0.0
else
  if [[ ! -f "$DB_PATH" ]]; then
    echo "Attempting Litestream restore..."
    if ! output=$(litestream restore -o "$DB_PATH" "$LITESTREAM_REPLICA_URL" 2>&1); then
      if echo "$output" | grep -qiE "cannot calc restore plan"; then
        echo "No replica snapshots found; starting with empty database."
      else
        echo "$output" >&2
        exit 1
      fi
    fi
  fi
  exec litestream replicate -exec "dstack server --host 0.0.0.0" "$DB_PATH" "$LITESTREAM_REPLICA_URL"
fi
