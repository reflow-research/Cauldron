// Frostbite VM Cargo build script
//
// Usage (Cargo.toml):
//   build = "../toolchain/scripts/frostbite-build.rs"
//
// Optional environment:
//   FROSTBITE_TOOLCHAIN=/path/to/frostbite/toolchain
//   FROSTBITE_LINKER_SCRIPT=/path/to/frostbite.ld
//
// This script also compiles toolchain/lib/crt0.c so `main()` works out of the box.

use std::env;
use std::path::{Path, PathBuf};
use std::process::Command;

fn resolve_toolchain(manifest_dir: &Path) -> PathBuf {
    if let Ok(dir) = env::var("FROSTBITE_TOOLCHAIN") {
        return PathBuf::from(dir);
    }

    let candidates = [
        manifest_dir.join("toolchain"),
        manifest_dir.join("../toolchain"),
        manifest_dir.join("../../toolchain"),
    ];

    for candidate in candidates {
        if candidate.join("lib/frostbite.ld").is_file() {
            return candidate;
        }
    }

    manifest_dir.to_path_buf()
}

fn main() {
    let manifest_dir = PathBuf::from(env::var("CARGO_MANIFEST_DIR").unwrap_or_else(|_| ".".into()));
    let toolchain = resolve_toolchain(&manifest_dir);

    let link_script = env::var("FROSTBITE_LINKER_SCRIPT")
        .map(PathBuf::from)
        .unwrap_or_else(|_| toolchain.join("lib/frostbite.ld"));
    let include_dir = toolchain.join("include");
    let crt0 = toolchain.join("lib/crt0.c");
    let alloc = toolchain.join("lib/frostbite_alloc.c");
    let softfloat = toolchain.join("lib/frostbite_softfloat.c");

    if !link_script.is_file() {
        panic!(
            "Frostbite linker script not found: {} (set FROSTBITE_TOOLCHAIN or FROSTBITE_LINKER_SCRIPT)",
            link_script.display()
        );
    }

    if !crt0.is_file() {
        panic!(
            "Frostbite crt0 not found: {} (set FROSTBITE_TOOLCHAIN)",
            crt0.display()
        );
    }

    let out_dir = PathBuf::from(env::var("OUT_DIR").unwrap());
    let crt0_obj = out_dir.join("crt0.o");
    let alloc_obj = out_dir.join("frostbite_alloc.o");
    let softfloat_obj = out_dir.join("frostbite_softfloat.o");

    let status = Command::new("clang")
        .args([
            "-target",
            "riscv64",
            "-march=rv64im",
            "-mabi=lp64",
            "-ffreestanding",
            "-fno-builtin",
            "-fno-stack-protector",
            "-fno-exceptions",
            "-fno-unwind-tables",
            "-fno-asynchronous-unwind-tables",
            "-c",
        ])
        .arg("-I")
        .arg(&include_dir)
        .arg(&crt0)
        .arg("-o")
        .arg(&crt0_obj)
        .status()
        .expect("Failed to invoke clang (is it installed?)");

    if !status.success() {
        panic!("Failed to compile crt0.c with clang");
    }

    if alloc.is_file() {
        let status = Command::new("clang")
            .args([
                "-target",
                "riscv64",
                "-march=rv64im",
                "-mabi=lp64",
                "-ffreestanding",
                "-fno-builtin",
                "-fno-stack-protector",
                "-fno-exceptions",
                "-fno-unwind-tables",
                "-fno-asynchronous-unwind-tables",
                "-c",
            ])
            .arg("-I")
            .arg(&include_dir)
            .arg(&alloc)
            .arg("-o")
            .arg(&alloc_obj)
            .status()
            .expect("Failed to invoke clang (is it installed?)");

        if !status.success() {
            panic!("Failed to compile frostbite_alloc.c with clang");
        }
    }

    if softfloat.is_file() {
        let status = Command::new("clang")
            .args([
                "-target",
                "riscv64",
                "-march=rv64im",
                "-mabi=lp64",
                "-ffreestanding",
                "-fno-builtin",
                "-fno-stack-protector",
                "-fno-exceptions",
                "-fno-unwind-tables",
                "-fno-asynchronous-unwind-tables",
                "-c",
            ])
            .arg("-I")
            .arg(&include_dir)
            .arg(&softfloat)
            .arg("-o")
            .arg(&softfloat_obj)
            .status()
            .expect("Failed to invoke clang (is it installed?)");

        if !status.success() {
            panic!("Failed to compile frostbite_softfloat.c with clang");
        }
    }

    println!("cargo:rustc-link-arg=-T{}", link_script.display());
    println!("cargo:rustc-link-arg={}", crt0_obj.display());
    if alloc.is_file() {
        println!("cargo:rustc-link-arg={}", alloc_obj.display());
    }
    if softfloat.is_file() {
        println!("cargo:rustc-link-arg={}", softfloat_obj.display());
    }
    println!("cargo:rustc-link-arg=--gc-sections");
    println!("cargo:rerun-if-changed={}", link_script.display());
    println!("cargo:rerun-if-changed={}", crt0.display());
    println!("cargo:rerun-if-changed={}", alloc.display());
    println!("cargo:rerun-if-changed={}", softfloat.display());
    println!("cargo:rerun-if-env-changed=FROSTBITE_TOOLCHAIN");
    println!("cargo:rerun-if-env-changed=FROSTBITE_LINKER_SCRIPT");

    if let Ok(target) = env::var("TARGET") {
        if !target.starts_with("riscv64") {
            println!(
                "cargo:warning=Frostbite build script expects a riscv64 target, got {}",
                target
            );
        }
    }
}
