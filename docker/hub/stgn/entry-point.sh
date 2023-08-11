pip3 install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple "dstack[all]" --upgrade --progress-bar off

if [ -n "${GOOGLE_APPLICATION_CREDENTIALS_JSON}" ]; then
  GOOGLE_APPLICATION_CREDENTIALS_DIR="${HOME}/.config/gcloud/"
  mkdir -p "${GOOGLE_APPLICATION_CREDENTIALS_DIR}"
  echo "${GOOGLE_APPLICATION_CREDENTIALS_JSON}" > "${GOOGLE_APPLICATION_CREDENTIALS_DIR}/application_default_credentials.json"
fi

if [[ -z "${LITESTREAM_REPLICA_URL}" ]]; then
  dstack start --host 0.0.0.0
else
  litestream restore -if-replica-exists -o ${HOME}/.dstack/hub/data2/sqlite.db ${LITESTREAM_REPLICA_URL}
  litestream replicate -exec "dstack start --host 0.0.0.0" ${HOME}/.dstack/hub/data2/sqlite.db ${LITESTREAM_REPLICA_URL}
fi