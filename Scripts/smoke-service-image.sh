#!/usr/bin/env bash
set -euo pipefail
: "${IMAGE:?IMAGE is required}"
: "${SERVICE_PATH:?SERVICE_PATH is required}"

case "$SERVICE_PATH" in
  Frontend) port=8080; health=/healthz ;;
  Runtime) port=8080; health=/actuator/health ;;
  Mapping_Proposal|Mapping_Converter) port=8000; health=/health ;;
  *) echo 'Unsupported service' >&2; exit 1 ;;
esac

container_id=$(docker run -d --read-only --tmpfs /tmp \
  --cap-drop=ALL --security-opt=no-new-privileges \
  -p "127.0.0.1::$port" "$IMAGE")
cleanup() {
  result=$?
  if [[ "$result" -ne 0 ]]; then docker logs "$container_id" >&2 || true; fi
  docker rm -f "$container_id" >/dev/null 2>&1 || true
}
trap cleanup EXIT
binding=$(docker port "$container_id" "$port/tcp")
base_url="http://127.0.0.1:${binding##*:}"
ready=false
for attempt in $(seq 1 60); do
  if curl --fail --silent "$base_url$health" >/dev/null; then ready=true; break; fi
  [[ "$(docker inspect "$container_id" --format '{{.State.Running}}')" == true ]] || break
  sleep 2
done
[[ "$ready" == true ]] || { echo "Container health check failed: $health" >&2; exit 1; }
if [[ "$SERVICE_PATH" == Frontend ]]; then
  curl --fail --silent "$base_url/" | grep -q 'id="root"'
  curl --fail --silent "$base_url/version-control" | grep -q 'id="root"'
fi
echo "Container smoke test passed for $SERVICE_PATH."
