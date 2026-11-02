#!/usr/bin/env bash
set -euo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
command -v python3 >/dev/null || { echo '缺少 python3；Debian/Ubuntu: apt install python3；RHEL: dnf install python3' >&2; exit 1; }
exec python3 "$HERE/install.py" "$@"
