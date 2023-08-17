#!/bin/bash
set -e

curl https://dstack-cli-downloads-stgn.s3.eu-west-1.amazonaws.com/dstack-$VERSION-py3-none-any.whl -O dstack-$VERSION-py3-none-any.whl
pip3 install "dstack-$VERSION-py3-none-any.whl[all]" --progress-bar off

if [ -n "${GOOGLE_APPLICATION_CREDENTIALS_JSON}" ]; then
  GOOGLE_APPLICATION_CREDENTIALS_DIR="${HOME}/.config/gcloud/"
  mkdir -p "${GOOGLE_APPLICATION_CREDENTIALS_DIR}"
  echo "${GOOGLE_APPLICATION_CREDENTIALS_JSON}" > "${GOOGLE_APPLICATION_CREDENTIALS_DIR}/application_default_credentials.json"
fi

if [[ -z "${LITESTREAM_REPLICA_URL}" ]]; then
  dstack start --host 0.0.0.0
else
  litestream restore -if-replica-exists -o ${HOME}/.dstack/server/data/sqlite.db ${LITESTREAM_REPLICA_URL}
  litestream replicate -exec "dstack start --host 0.0.0.0" ${HOME}/.dstack/server/data/sqlite.db ${LITESTREAM_REPLICA_URL}
fi