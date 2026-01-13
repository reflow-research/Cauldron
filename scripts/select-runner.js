#!/usr/bin/env node
const fs = require("fs");
const path = require("path");

function platformTag() {
  const platform = process.platform;
  const arch = process.arch;
  if (platform === "darwin") {
    if (arch === "arm64") return "darwin-arm64";
    if (arch === "x64") return "darwin-x64";
  }
  if (platform === "linux") {
    if (arch === "x64") return "linux-x64";
    if (arch === "arm64") return "linux-arm64";
  }
  if (platform === "win32") {
    if (arch === "x64") return "windows-x64";
  }
  return null;
}

function candidates(root) {
  const tag = platformTag();
  const runner = process.platform === "win32" ? "frostbite-run-onchain.exe" : "frostbite-run-onchain";
  const out = [];
  if (tag) {
    out.push(path.join(root, "cauldron", "bin", tag, runner));
    out.push(path.join(root, "cauldron", "toolchain", "bin", tag, runner));
  }
  out.push(path.join(root, "cauldron", "bin", runner));
  out.push(path.join(root, "cauldron", "toolchain", "bin", runner));
  return out;
}

function main() {
  const args = process.argv.slice(2);
  const rootIdx = args.indexOf("--root");
  const copy = args.includes("--copy");
  const root = rootIdx !== -1 && args[rootIdx + 1]
    ? path.resolve(args[rootIdx + 1])
    : path.resolve(__dirname, "..");
  const runner = process.platform === "win32" ? "frostbite-run-onchain.exe" : "frostbite-run-onchain";
  const dest = path.join(root, "cauldron", "bin", runner);

  for (const candidate of candidates(root)) {
    if (fs.existsSync(candidate)) {
      if (copy) {
        fs.mkdirSync(path.dirname(dest), { recursive: true });
        fs.copyFileSync(candidate, dest);
        console.log(dest);
      } else {
        console.log(candidate);
      }
      return;
    }
  }

  console.error("No frostbite-run-onchain binary found for this platform");
  process.exit(1);
}

main();
