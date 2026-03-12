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
    echo "Starting db restore"
    litestream restore -if-replica-exists -o "$DB_PATH" "$LITESTREAM_REPLICA_URL"
    echo "Finished db restore"
  fi
  exec litestream replicate -exec "dstack server --host 0.0.0.0" "$DB_PATH" "$LITESTREAM_REPLICA_URL"
fi
