# Cauldron Bundled Binaries

Platform-specific binaries live in subdirectories like:

- `darwin-arm64/`
- `darwin-x64/`
- `linux-x64/`
- `linux-arm64/`
- `windows-x64/`

The CLI auto-discovers the correct platform path. Alternatively set
`FROSTBITE_RUN_ONCHAIN` to an absolute path. The CLI also checks
`cauldron/toolchain/bin/<platform>` if you bundle the toolchain.

If you need to rebuild the binary locally (for example, on another platform):

```sh
cargo build --release --bin frostbite-run-onchain --no-default-features --features cli
cp target/release/frostbite-run-onchain cauldron/bin/<platform>/
```

Or use the helper script to build + stage into `bin/<platform>`:

```sh
# If cauldron is a standalone repo, set FROSTBITE_REPO_ROOT=/path/to/frostbite
./scripts/build-runner-binaries.sh
```
