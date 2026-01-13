# Frostbite Toolchain Examples

- `c_cpp/` - C/C++ example using `frostbite.h` and `fb-cc`/CMake (includes syscall smoke test)
- `rust/` - Rust example using `frostbite-sdk` and Cargo (includes syscall smoke test)

For multi-transaction runs, use `frostbite-run-onchain --vm-save/--vm-file` to resume,
and `--ram-save/--ram-file` to reuse mapped RAM accounts. The runner prints the
segment mapping so you can match `FB_SEGMENT_ADDR(segment, offset)` in code.

By default `frostbite-run-onchain` creates one RAM account. Use `--ram-count 0`
to disable.

For local runs of on-chain builds, `frostbite-run` supports `--ram-count` and
`--ram-bytes` with the same segment mapping (segments 1-15). If your program
uses `fb_yield` or resumable syscalls, pass `--max-tx N` (or `--max-tx 0`) to
auto-resume locally.

For on-chain runs outside the repo, set `FROSTBITE_PROGRAM_ID` or pass `--program-id`.
