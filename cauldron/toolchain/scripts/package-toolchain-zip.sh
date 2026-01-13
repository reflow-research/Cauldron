#!/bin/bash
# Package the toolchain directory for standalone distribution as a ZIP.
# Usage: toolchain/scripts/package-toolchain-zip.sh [output.zip]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TOOLCHAIN_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_DIR="$(dirname "$TOOLCHAIN_DIR")"
BIN_DIR="$TOOLCHAIN_DIR/bin"

OUT="${1:-frostbite-toolchain-linux-x86_64.zip}"

if [ "$(uname -s)" != "Linux" ] || [ "$(uname -m)" != "x86_64" ]; then
    echo "Warning: packaging on $(uname -s) $(uname -m); expected Linux x86_64." >&2
fi

mkdir -p "$BIN_DIR"

# Build and bundle CLI tools if we are in the full repo.
if [ -f "$PROJECT_DIR/Cargo.toml" ]; then
    echo "Building frostbite-run binaries..."
    (cd "$PROJECT_DIR" && cargo build --bins --no-default-features --features cli --release)
    cp -f "$PROJECT_DIR/target/release/frostbite-run" "$BIN_DIR/"
    cp -f "$PROJECT_DIR/target/release/frostbite-run-onchain" "$BIN_DIR/"
else
    if [ ! -f "$BIN_DIR/frostbite-run" ] || [ ! -f "$BIN_DIR/frostbite-run-onchain" ]; then
        echo "Missing frostbite-run binaries. Build them and place in toolchain/bin." >&2
        exit 1
    fi
fi

BASE_DIR="$(dirname "$TOOLCHAIN_DIR")"
NAME="$(basename "$TOOLCHAIN_DIR")"

if command -v python3 >/dev/null 2>&1; then
    BASE_DIR="$BASE_DIR" NAME="$NAME" OUT="$OUT" python3 - <<'PY'
import os
import zipfile

base_dir = os.environ["BASE_DIR"]
toolchain_name = os.environ["NAME"]
zip_path = os.environ["OUT"]

skip_dirs = {".git", "__pycache__", "build", "target"}
skip_ext = {".o", ".elf", ".bin"}

root_dir = os.path.join(base_dir, toolchain_name)

with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for name in files:
            if name.startswith("."):
                continue
            _, ext = os.path.splitext(name)
            if ext in skip_ext and "examples" in root:
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, base_dir)
            zf.write(path, rel)

print(f"Wrote {zip_path}")
PY
else
    if ! command -v zip >/dev/null 2>&1; then
        echo "Neither python3 nor zip is available to create a ZIP." >&2
        exit 1
    fi
    (cd "$BASE_DIR" && zip -r "$OUT" "$NAME" \
        -x "*/.git/*" "*/__pycache__/*" "*/build/*" "*/target/*" \
        -x "*/examples/*/*.o" "*/examples/*/*.elf" "*/examples/*/*.bin")
    echo "Wrote $OUT"
fi
