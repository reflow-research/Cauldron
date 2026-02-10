#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/uninstall-global.sh [options]

Uninstall globally installed Cauldron package from this environment.

Options:
  --python <exe>          Python executable to use (default: python3)
  --no-break-system-packages
                          Do not pass --break-system-packages to pip
  -h, --help              Show this help

Example:
  ./scripts/uninstall-global.sh
EOF
}

PYTHON_EXE="python3"
BREAK_SYSTEM_PACKAGES=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --python)
      PYTHON_EXE="$2"
      shift 2
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

pip_args=()
if [[ "$BREAK_SYSTEM_PACKAGES" -eq 1 ]]; then
  if "$PYTHON_EXE" -m pip help uninstall 2>/dev/null | grep -q -- "--break-system-packages"; then
    pip_args+=(--break-system-packages)
  else
    echo "WARN: pip does not support --break-system-packages; continuing without it."
  fi
fi

echo "+ $PYTHON_EXE -m pip uninstall -y ${pip_args[*]} frostbite-modelkit"
"$PYTHON_EXE" -m pip uninstall -y "${pip_args[@]}" frostbite-modelkit

if command -v cauldron >/dev/null 2>&1; then
  echo "Note: 'cauldron' still resolves to: $(command -v cauldron)"
  echo "If this is unexpected, another environment/package may provide it."
else
  echo "Cauldron entrypoint removed from PATH."
fi
