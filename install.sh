#!/usr/bin/env bash
set -euo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ $# == 0 || "${1:-}" == --wizard ]]; then
  missing=()
  command -v python3 >/dev/null || missing+=(python3)
  command -v curl >/dev/null || missing+=(curl)
  command -v flock >/dev/null && command -v unshare >/dev/null || missing+=(util-linux)
  if ((${#missing[@]})); then
    echo "缺少系统包: ${missing[*]}"
    read -r -p '使用现有系统源安装？输入 YES: ' answer
    [[ "$answer" == YES ]] || exit 1
    if command -v apt-get >/dev/null; then
      apt-get install --no-upgrade "${missing[@]}"
    elif command -v dnf >/dev/null; then
      dnf install "${missing[@]}"
    else
      echo '不支持的包管理器'; exit 1
    fi
  fi
fi
command -v python3 >/dev/null || { echo '缺少 python3' >&2; exit 1; }
if [[ $# == 0 || "${1:-}" == --wizard || "${1:-}" == --bundle ]]; then
  exec python3 "$HERE/setup-wizard.py" "$@"
fi
exec python3 "$HERE/install.py" "$@"
