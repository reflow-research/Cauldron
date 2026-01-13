#!/bin/bash
# Package the toolchain directory for standalone distribution.
# Usage: toolchain/scripts/package-toolchain.sh [output.tar.gz]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TOOLCHAIN_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_DIR="$(dirname "$TOOLCHAIN_DIR")"
BIN_DIR="$TOOLCHAIN_DIR/bin"

mkdir -p "$BIN_DIR"

# Optionally bundle CLI binaries if they exist.
if [ -f "$PROJECT_DIR/target/release/frostbite-run" ]; then
    cp -f "$PROJECT_DIR/target/release/frostbite-run" "$BIN_DIR/"
fi

if [ -f "$PROJECT_DIR/target/release/frostbite-run-onchain" ]; then
    cp -f "$PROJECT_DIR/target/release/frostbite-run-onchain" "$BIN_DIR/"
fi

OUT="${1:-frostbite-toolchain.tar.gz}"
BASE_DIR="$(dirname "$TOOLCHAIN_DIR")"
NAME="$(basename "$TOOLCHAIN_DIR")"

( cd "$BASE_DIR" && tar -czf "$OUT" "$NAME" )

echo "Wrote $OUT"
