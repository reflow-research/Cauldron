#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CAULDRON_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)

FROSTBITE_ROOT=${FROSTBITE_REPO_ROOT:-}
if [ -z "$FROSTBITE_ROOT" ]; then
  if [ -f "${CAULDRON_ROOT}/../Cargo.toml" ] && grep -q 'name = "frostbite"' "${CAULDRON_ROOT}/../Cargo.toml"; then
    FROSTBITE_ROOT=$(cd "${CAULDRON_ROOT}/.." && pwd)
  else
    echo "Set FROSTBITE_REPO_ROOT to the frostbite repo root." >&2
    exit 1
  fi
fi

TARGET=${TARGET:-}
OUT_DIR=${OUT_DIR:-}

while [ $# -gt 0 ]; do
  case "$1" in
    --target)
      TARGET="$2"
      shift 2
      ;;
    --out)
      OUT_DIR="$2"
      shift 2
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 1
      ;;
  esac
done

platform_tag_from_target() {
  case "$1" in
    aarch64-apple-darwin) echo "darwin-arm64" ;;
    x86_64-apple-darwin) echo "darwin-x64" ;;
    aarch64-unknown-linux-gnu|aarch64-unknown-linux-musl) echo "linux-arm64" ;;
    x86_64-unknown-linux-gnu|x86_64-unknown-linux-musl) echo "linux-x64" ;;
    x86_64-pc-windows-msvc|x86_64-pc-windows-gnu) echo "windows-x64" ;;
    *) echo "" ;;
  esac
}

platform_tag_from_host() {
  local os
  local arch
  os=$(uname -s)
  arch=$(uname -m)
  case "$os" in
    Darwin) os="darwin" ;;
    Linux) os="linux" ;;
    MINGW*|MSYS*|CYGWIN*) os="windows" ;;
    *) echo ""; return 0 ;;
  esac
  case "$arch" in
    arm64|aarch64) arch="arm64" ;;
    x86_64|amd64) arch="x64" ;;
    *) echo ""; return 0 ;;
  esac
  echo "${os}-${arch}"
}

runner_name_from_target() {
  case "$1" in
    x86_64-pc-windows-msvc|x86_64-pc-windows-gnu) echo "frostbite-run-onchain.exe" ;;
    *) echo "frostbite-run-onchain" ;;
  esac
}

runner_name_from_host() {
  local os
  os=$(uname -s)
  case "$os" in
    MINGW*|MSYS*|CYGWIN*) echo "frostbite-run-onchain.exe" ;;
    *) echo "frostbite-run-onchain" ;;
  esac
}

PLATFORM_TAG=""
if [ -n "$TARGET" ]; then
  PLATFORM_TAG=$(platform_tag_from_target "$TARGET")
else
  PLATFORM_TAG=$(platform_tag_from_host)
fi

if [ -z "$PLATFORM_TAG" ]; then
  echo "Unsupported platform/target; set --target or OUT_DIR explicitly." >&2
  exit 1
fi

BIN_NAME=$(runner_name_from_host)
if [ -n "$TARGET" ]; then
  BIN_NAME=$(runner_name_from_target "$TARGET")
fi

if [ -z "$OUT_DIR" ]; then
  OUT_DIR="${CAULDRON_ROOT}/cauldron/bin/${PLATFORM_TAG}"
fi

BUILD_ARGS=("--release" "--bin" "frostbite-run-onchain" "--no-default-features" "--features" "cli")
if [ -n "$TARGET" ]; then
  BUILD_ARGS+=("--target" "$TARGET")
fi

echo "Building frostbite-run-onchain (${PLATFORM_TAG})"
(
  cd "${FROSTBITE_ROOT}"
  cargo build "${BUILD_ARGS[@]}"
)

BIN_SRC="${FROSTBITE_ROOT}/target/release/${BIN_NAME}"
if [ -n "$TARGET" ]; then
  BIN_SRC="${FROSTBITE_ROOT}/target/${TARGET}/release/${BIN_NAME}"
fi

if [ ! -f "$BIN_SRC" ]; then
  echo "Binary not found: ${BIN_SRC}" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"
cp -f "$BIN_SRC" "$OUT_DIR/${BIN_NAME}"

echo "Staged: $OUT_DIR/${BIN_NAME}"
