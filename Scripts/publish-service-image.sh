#!/usr/bin/env bash
# Publish the container already built and smoke-tested by Testing CI. Never rebuild it.
set -euo pipefail
docker load --input "$RUNNER_TEMP/service-image/image.tar"
revision=$(docker image inspect service-ci:local --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')
[[ "$revision" == "$SOURCE_SHA" ]] || { echo '::error::CI image revision does not match'; exit 1; }

# Keep Testing away from the legacy :latest bootstrap image used by production.
# Both environments deploy by digest; :testing is only a convenient registry alias.
for tag in "sha-$SOURCE_SHA" testing; do
  docker tag service-ci:local "$IMAGE_BASE:$tag"
  docker push "$IMAGE_BASE:$tag"
done
digests=$(docker image inspect "$IMAGE_BASE:sha-$SOURCE_SHA" --format '{{range .RepoDigests}}{{println .}}{{end}}')
image=''
while IFS= read -r digest; do
  if [[ "$digest" == "$IMAGE_BASE"@sha256:* ]]; then
    image="$digest"
    break
  fi
done <<< "$digests"
[[ "$image" == "$IMAGE_BASE"@sha256:* ]] || { echo '::error::No registry digest returned'; exit 1; }
printf 'image=%s\nsource-sha=%s\n' "$image" "$SOURCE_SHA" >> "$GITHUB_OUTPUT"
