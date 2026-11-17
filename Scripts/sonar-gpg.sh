#!/usr/bin/env bash
# Keep signature verification; a stalled keyserver must not block GPG for minutes.
exec timeout --kill-after=5s 30s /usr/bin/gpg "$@"
