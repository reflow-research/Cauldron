#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/install-global.sh [options]

Install Cauldron globally from this cloned repo.

Options:
  --python <exe>          Python executable to use (default: python3)
  --extras <list>         Optional dependency extras (default: tui,train)
  --no-editable           Install non-editable instead of editable
  --no-break-system-packages
                          Do not pass --break-system-packages to pip
  -h, --help              Show this help

Examples:
  ./scripts/install-global.sh
  ./scripts/install-global.sh --python python3.11 --extras tui
EOF
}

PYTHON_EXE="python3"
EXTRAS="tui,train"
EDITABLE=1
BREAK_SYSTEM_PACKAGES=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --python)
      PYTHON_EXE="$2"
      shift 2
      ;;
    --extras)
      EXTRAS="$2"
      shift 2
      ;;
    --no-editable)
      EDITABLE=0
      shift
      ;;
    --no-break-system-packages)
      BREAK_SYSTEM_PACKAGES=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if ! command -v "$PYTHON_EXE" >/dev/null 2>&1; then
  echo "Python executable not found: $PYTHON_EXE" >&2
  exit 1
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

target="."
if [[ -n "$EXTRAS" ]]; then
  target=".[${EXTRAS}]"
fi

pip_args=()
if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  pip_args+=(--user)
fi
if [[ "$BREAK_SYSTEM_PACKAGES" -eq 1 ]]; then
  if "$PYTHON_EXE" -m pip help install 2>/dev/null | grep -q -- "--break-system-packages"; then
    pip_args+=(--break-system-packages)
  else
    echo "WARN: pip does not support --break-system-packages; continuing without it."
  fi
fi
if [[ "$EDITABLE" -eq 1 ]]; then
  pip_args+=(-e)
fi

echo "Installing from: $repo_root"
echo "+ $PYTHON_EXE -m pip install ${pip_args[*]} $target"
"$PYTHON_EXE" -m pip install "${pip_args[@]}" "$target"

script_dir="$("$PYTHON_EXE" - <<'PY'
import os
import site
import sys
if os.environ.get("VIRTUAL_ENV"):
    print(os.path.dirname(sys.executable))
else:
    base = site.getuserbase()
    if os.name == "nt":
        print(os.path.join(base, "Scripts"))
    else:
        print(os.path.join(base, "bin"))
PY
)"

cauldron_path="$script_dir/cauldron"
if [[ -f "$cauldron_path" || -x "$cauldron_path" ]]; then
  echo "Installed CLI entrypoint: $cauldron_path"
fi

if command -v cauldron >/dev/null 2>&1; then
  echo "Cauldron is on PATH: $(command -v cauldron)"
  echo "Done. Run: cauldron --help"
  exit 0
fi

echo
echo "Cauldron installed, but your shell PATH does not include:"
echo "  $script_dir"
echo
echo "Add this and restart your shell:"
echo "  export PATH=\"$script_dir:\$PATH\""
echo
echo "Then run:"
echo "  cauldron --help"
