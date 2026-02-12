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
  --global                Install to interpreter/global site-packages (default)
  --user                  Install to user site-packages (~/.local)
  --no-editable           Install non-editable instead of editable
  --no-break-system-packages
                          Do not pass --break-system-packages to pip
  -h, --help              Show this help

Examples:
  ./scripts/install-global.sh
  ./scripts/install-global.sh --user
  ./scripts/install-global.sh --python python3.11 --extras tui
EOF
}

PYTHON_EXE="python3"
EXTRAS="tui,train"
EDITABLE=1
BREAK_SYSTEM_PACKAGES=1
INSTALL_SCOPE="global"
PIP_CMD=()

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
    --global)
      INSTALL_SCOPE="global"
      shift
      ;;
    --user)
      INSTALL_SCOPE="user"
      shift
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

bootstrap_pip_with_get_pip() {
  local get_pip_url="https://bootstrap.pypa.io/get-pip.py"
  local get_pip_script
  get_pip_script="$(mktemp "${TMPDIR:-/tmp}/cauldron-get-pip.XXXXXX.py")"

  if command -v curl >/dev/null 2>&1; then
    if ! curl -fsSL "$get_pip_url" -o "$get_pip_script"; then
      rm -f "$get_pip_script"
      return 1
    fi
  elif command -v wget >/dev/null 2>&1; then
    if ! wget -qO "$get_pip_script" "$get_pip_url"; then
      rm -f "$get_pip_script"
      return 1
    fi
  else
    if ! "$PYTHON_EXE" - "$get_pip_url" "$get_pip_script" <<'PY'
import pathlib
import sys
import urllib.request

url = sys.argv[1]
dest = pathlib.Path(sys.argv[2])
dest.write_bytes(urllib.request.urlopen(url, timeout=30).read())
PY
    then
      rm -f "$get_pip_script"
      return 1
    fi
  fi

  if ! PIP_BREAK_SYSTEM_PACKAGES=1 "$PYTHON_EXE" "$get_pip_script" --user; then
    # Fallback for environments where pip/get-pip does not recognize
    # break-system-packages controls.
    if ! "$PYTHON_EXE" "$get_pip_script" --user; then
      rm -f "$get_pip_script"
      return 1
    fi
  fi

  rm -f "$get_pip_script"
  return 0
}

resolve_pip_cmd() {
  if "$PYTHON_EXE" -m pip --version >/dev/null 2>&1; then
    PIP_CMD=("$PYTHON_EXE" -m pip)
    return 0
  fi

  echo "pip is not available for $PYTHON_EXE. Attempting bootstrap via ensurepip..."
  if ! ensurepip_output="$("$PYTHON_EXE" -m ensurepip --upgrade 2>&1)"; then
    echo "WARN: ensurepip failed; checking for matching pip binary." >&2
    echo "$ensurepip_output" >&2
  fi

  if "$PYTHON_EXE" -m pip --version >/dev/null 2>&1; then
    PIP_CMD=("$PYTHON_EXE" -m pip)
    return 0
  fi

  python_mm="$("$PYTHON_EXE" - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"

  for candidate in pip3 pip; do
    if ! command -v "$candidate" >/dev/null 2>&1; then
      continue
    fi

    pip_mm="$("$candidate" --version 2>/dev/null | sed -nE 's/.*\(python ([0-9]+\.[0-9]+)\).*/\1/p')"
    if [[ "$pip_mm" == "$python_mm" ]]; then
      echo "WARN: Falling back to '$candidate' because '$PYTHON_EXE -m pip' is unavailable."
      PIP_CMD=("$candidate")
      return 0
    fi
  done

  echo "WARN: Could not find pip via ensurepip or pip binaries. Attempting get-pip bootstrap." >&2
  if bootstrap_pip_with_get_pip && "$PYTHON_EXE" -m pip --version >/dev/null 2>&1; then
    PIP_CMD=("$PYTHON_EXE" -m pip)
    return 0
  fi

  echo "ERROR: Could not find a usable pip for $PYTHON_EXE." >&2
  echo "Install pip for this interpreter and rerun this script." >&2
  return 1
}

resolve_pip_cmd

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if [[ -n "${VIRTUAL_ENV:-}" && "$INSTALL_SCOPE" == "user" ]]; then
  echo "WARN: --user is ignored inside a virtual environment; installing into the active venv."
  INSTALL_SCOPE="global"
fi

target="."
if [[ -n "$EXTRAS" ]]; then
  target=".[${EXTRAS}]"
fi

editable_install_args=()
if [[ "$EDITABLE" -eq 1 ]]; then
  editable_install_args+=(-e)
fi

break_system_args=()
if [[ "$BREAK_SYSTEM_PACKAGES" -eq 1 && -z "${VIRTUAL_ENV:-}" ]]; then
  if "${PIP_CMD[@]}" help install 2>/dev/null | grep -q -- "--break-system-packages"; then
    break_system_args+=(--break-system-packages)
  else
    echo "WARN: pip does not support --break-system-packages; continuing without it."
  fi
fi

global_install_args=("${break_system_args[@]}" "${editable_install_args[@]}")
user_install_args=(--user "${break_system_args[@]}" "${editable_install_args[@]}")

echo "Installing from: $repo_root"
install_mode_used="$INSTALL_SCOPE"
if [[ "$INSTALL_SCOPE" == "user" ]]; then
  echo "+ ${PIP_CMD[*]} install ${user_install_args[*]} $target"
  "${PIP_CMD[@]}" install "${user_install_args[@]}" "$target"
else
  echo "+ ${PIP_CMD[*]} install ${global_install_args[*]} $target"
  if ! "${PIP_CMD[@]}" install "${global_install_args[@]}" "$target"; then
    if [[ -z "${VIRTUAL_ENV:-}" ]]; then
      echo "WARN: Global install failed. Retrying with --user for compatibility."
      echo "+ ${PIP_CMD[*]} install ${user_install_args[*]} $target"
      "${PIP_CMD[@]}" install "${user_install_args[@]}" "$target"
      install_mode_used="user"
    else
      exit 1
    fi
  fi
fi

script_dir="$(CAULDRON_INSTALL_MODE="$install_mode_used" "$PYTHON_EXE" - <<'PY'
import os
import site
import sys
import sysconfig
install_mode = os.environ.get("CAULDRON_INSTALL_MODE", "global")
if os.environ.get("VIRTUAL_ENV"):
    print(os.path.dirname(sys.executable))
elif install_mode == "user":
    base = site.getuserbase()
    if os.name == "nt":
        print(os.path.join(base, "Scripts"))
    else:
        print(os.path.join(base, "bin"))
else:
    print(sysconfig.get_path("scripts"))
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
