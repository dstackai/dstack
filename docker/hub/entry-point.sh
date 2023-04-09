if [[ -z "${LITESTREAM_REPLICA_URL}" ]]; then
  dstack hub start --host 0.0.0.0
else
  litestream restore -if-replica-exists -o /root/.dstack/hub/data/sqlite.db ${LITESTREAM_REPLICA_URL}
  litestream replicate -exec "dstack hub start --host 0.0.0.0" /root/.dstack/hub/data/sqlite.db ${LITESTREAM_REPLICA_URL}
fi