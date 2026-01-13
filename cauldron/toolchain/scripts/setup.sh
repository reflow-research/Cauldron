#!/bin/bash
# Frostbite Toolchain Setup Script
#
# This script checks for required tools and sets up the environment
# for building programs for the Frostbite RISC-V VM.
#
# Usage:
#   source toolchain/scripts/setup.sh
#   toolchain/scripts/setup.sh --persist
#
# Requirements:
#   - LLVM/Clang with RISC-V support
#   - LLD linker
#   - Rust (for frostbite-run)

set -e

PERSIST=0
EXPLICIT_NO_PERSIST=0

for arg in "$@"; do
    case "$arg" in
        --persist)
            PERSIST=1
            ;;
        --no-persist)
            EXPLICIT_NO_PERSIST=1
            ;;
        -h|--help)
            echo "Frostbite Toolchain Setup"
            echo ""
            echo "Usage:"
            echo "  source toolchain/scripts/setup.sh"
            echo "  toolchain/scripts/setup.sh --persist"
            echo ""
            echo "Options:"
            echo "  --persist     Write environment exports to your shell profile"
            echo "  --no-persist  Do not modify shell profile"
            echo ""
            return 0 2>/dev/null || exit 0
            ;;
    esac
done

is_sourced() {
    if [ -n "${BASH_SOURCE:-}" ]; then
        [ "${BASH_SOURCE[0]}" != "$0" ] && return 0 || return 1
    fi
    if [ -n "${ZSH_EVAL_CONTEXT:-}" ]; then
        case "$ZSH_EVAL_CONTEXT" in *:file) return 0 ;; esac
    fi
    return 1
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLCHAIN_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_DIR="$(dirname "$TOOLCHAIN_DIR")"
BIN_DIR="$TOOLCHAIN_DIR/bin"

echo "Frostbite Toolchain Setup"
echo "========================="
echo ""

# Check for required tools
check_tool() {
    local tool=$1
    local package=$2
    if command -v "$tool" &>/dev/null; then
        echo "[OK] $tool found: $(command -v "$tool")"
        return 0
    else
        echo "[MISSING] $tool not found"
        echo "  Install with: $package"
        return 1
    fi
}

persist_env() {
    local shell_name rc_file
    shell_name="$(basename "${SHELL:-}")"

    case "$shell_name" in
        bash)
            rc_file="${BASHRC:-$HOME/.bashrc}"
            ;;
        zsh)
            rc_file="${ZDOTDIR:-$HOME}/.zshrc"
            ;;
        fish)
            rc_file="$HOME/.config/fish/conf.d/frostbite.fish"
            ;;
        *)
            rc_file="$HOME/.profile"
            ;;
    esac

    if [ "$shell_name" = "fish" ]; then
        mkdir -p "$(dirname "$rc_file")"
        cat > "$rc_file" <<EOF
# >>> frostbite toolchain >>>
set -gx FROSTBITE_HOME "$PROJECT_DIR"
set -gx FROSTBITE_TOOLCHAIN "$TOOLCHAIN_DIR"
set -gx FROSTBITE_INCLUDE "$TOOLCHAIN_DIR/include"
set -gx FROSTBITE_LIB "$TOOLCHAIN_DIR/lib"
fish_add_path -g "$BIN_DIR" "$PROJECT_DIR/target/release" "$TOOLCHAIN_DIR/scripts"
# <<< frostbite toolchain <<<
EOF
        echo "[OK] Updated $rc_file"
        return 0
    fi

    local marker_start="# >>> frostbite toolchain >>>"
    local marker_end="# <<< frostbite toolchain <<<"

    if [ -f "$rc_file" ] && grep -q "$marker_start" "$rc_file"; then
        awk -v start="$marker_start" -v end="$marker_end" '
            $0 == start {skip=1; next}
            $0 == end {skip=0; next}
            !skip {print}
        ' "$rc_file" > "${rc_file}.tmp"
        mv "${rc_file}.tmp" "$rc_file"
    fi

    cat >> "$rc_file" <<EOF
$marker_start
export FROSTBITE_HOME="$PROJECT_DIR"
export FROSTBITE_TOOLCHAIN="$TOOLCHAIN_DIR"
export FROSTBITE_INCLUDE="$TOOLCHAIN_DIR/include"
export FROSTBITE_LIB="$TOOLCHAIN_DIR/lib"
export PATH="$BIN_DIR:$PROJECT_DIR/target/release:$TOOLCHAIN_DIR/scripts:\$PATH"
$marker_end
EOF

    echo "[OK] Updated $rc_file"
}

MISSING=0

echo "Checking required tools..."
echo ""

check_tool clang "sudo apt install clang" || MISSING=1
check_tool ld.lld "sudo apt install lld" || MISSING=1
check_tool llvm-objcopy "sudo apt install llvm" || MISSING=1
check_tool llvm-objdump "sudo apt install llvm" || MISSING=1
check_tool cargo "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh" || MISSING=1

echo ""

# Check clang RISC-V support
if command -v clang &>/dev/null; then
    if clang --target=riscv64 -march=rv64imac -c -x c /dev/null -o /dev/null 2>/dev/null; then
        echo "[OK] Clang has RISC-V 64-bit support"
    else
        echo "[WARN] Clang may not have full RISC-V support"
        echo "  Try: sudo apt install clang llvm"
        MISSING=1
    fi
fi

echo ""

if [ $MISSING -eq 1 ]; then
    echo "Some tools are missing. Please install them and re-run this script."
    echo ""
    echo "Quick install (Ubuntu/Debian):"
    echo "  sudo apt install clang lld llvm"
    echo ""
    return 1 2>/dev/null || exit 1
fi

RUNNER="$PROJECT_DIR/target/release/frostbite-run"
RUNNER_ONCHAIN="$PROJECT_DIR/target/release/frostbite-run-onchain"
BIN_RUNNER="$BIN_DIR/frostbite-run"
BIN_RUNNER_ONCHAIN="$BIN_DIR/frostbite-run-onchain"

# Build CLI tools if we are in the full repo
if [ -f "$PROJECT_DIR/Cargo.toml" ]; then
    if [ ! -f "$RUNNER" ] || [ ! -f "$RUNNER_ONCHAIN" ]; then
        echo "Building CLI tools..."
        (cd "$PROJECT_DIR" && cargo build --bins --no-default-features --features cli --release)
    fi
else
    echo "[INFO] No Cargo.toml found; skipping CLI build (standalone toolchain)."
fi

if [ -f "$RUNNER" ]; then
    echo "[OK] frostbite-run (local): $RUNNER"
elif [ -f "$BIN_RUNNER" ]; then
    echo "[OK] frostbite-run (local): $BIN_RUNNER"
else
    echo "[WARN] frostbite-run not found (install or add to toolchain/bin)"
fi

if [ -f "$RUNNER_ONCHAIN" ]; then
    echo "[OK] frostbite-run-onchain (Solana): $RUNNER_ONCHAIN"
elif [ -f "$BIN_RUNNER_ONCHAIN" ]; then
    echo "[OK] frostbite-run-onchain (Solana): $BIN_RUNNER_ONCHAIN"
else
    echo "[WARN] frostbite-run-onchain not found (install or add to toolchain/bin)"
fi

# Set up environment variables
export FROSTBITE_HOME="$PROJECT_DIR"
export FROSTBITE_TOOLCHAIN="$TOOLCHAIN_DIR"
export FROSTBITE_INCLUDE="$TOOLCHAIN_DIR/include"
export FROSTBITE_LIB="$TOOLCHAIN_DIR/lib"

# Add to PATH
export PATH="$BIN_DIR:$PROJECT_DIR/target/release:$TOOLCHAIN_DIR/scripts:$PATH"

if [ $EXPLICIT_NO_PERSIST -eq 1 ]; then
    PERSIST=0
fi

if ! is_sourced; then
    if [ $EXPLICIT_NO_PERSIST -eq 0 ]; then
        PERSIST=1
    fi
    SOURCED=0
else
    SOURCED=1
fi

if [ $PERSIST -eq 1 ]; then
    persist_env
    if [ $SOURCED -eq 0 ]; then
        echo "[INFO] Open a new shell or source your profile to pick up PATH changes."
    fi
elif [ $SOURCED -eq 0 ]; then
    echo "[WARN] setup.sh was executed, not sourced. PATH changes will not persist."
    echo "       Re-run with: source toolchain/scripts/setup.sh"
    echo "       Or run: toolchain/scripts/setup.sh --persist"
fi

echo ""
echo "Environment configured:"
echo "  FROSTBITE_HOME=$FROSTBITE_HOME"
echo "  FROSTBITE_TOOLCHAIN=$FROSTBITE_TOOLCHAIN"
echo "  FROSTBITE_INCLUDE=$FROSTBITE_INCLUDE"
echo "  FROSTBITE_LIB=$FROSTBITE_LIB"
echo ""
echo "You can now use:"
echo "  fb-cc my_program.c -o my_program.elf      # Compile C to RISC-V ELF"
echo "  frostbite-run my_program.elf              # Run locally (no Solana)"
echo "  frostbite-run-onchain my_program.elf      # Run on Solana cluster"
echo ""
echo "For on-chain execution, start a local validator first:"
echo "  solana-test-validator"
echo "  solana program deploy target/deploy/frostbite.so"
echo ""
echo "Setup complete!"
