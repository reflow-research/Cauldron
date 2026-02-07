const fs = require("fs");
const path = require("path");
const toml = require("toml");
const {
  Connection,
  Keypair,
  PublicKey,
  Transaction,
  TransactionInstruction,
  sendAndConfirmTransaction,
  ComputeBudgetProgram,
} = require("@solana/web3.js");

const EXECUTE_OP = 2;
const EXECUTE_V3_OP = 43;
const SEGMENT_KIND_WEIGHTS = 1;
const SEGMENT_KIND_RAM = 2;

function parseArgs(argv) {
  const out = {};
  for (let i = 2; i < argv.length; i += 1) {
    const arg = argv[i];
    if (!arg.startsWith("--")) continue;
    const key = arg.slice(2);
    if (i + 1 < argv.length && !argv[i + 1].startsWith("--")) {
      out[key] = argv[i + 1];
      i += 1;
    } else {
      out[key] = true;
    }
  }
  return out;
}

function loadToml(filePath) {
  return toml.parse(fs.readFileSync(filePath, "utf8"));
}

function loadKeypair(filePath) {
  const raw = JSON.parse(fs.readFileSync(filePath, "utf8"));
  return Keypair.fromSecretKey(Uint8Array.from(raw));
}

function resolveAccountsPath(accountsPath, value) {
  if (!value) return null;
  let resolved = value;
  if (resolved.startsWith("~")) {
    resolved = path.join(process.env.HOME || "", resolved.slice(1));
  }
  if (path.isAbsolute(resolved)) {
    return resolved;
  }
  return path.resolve(path.dirname(path.resolve(accountsPath)), resolved);
}

function parseVmSeed(vmEntry) {
  const raw = vmEntry?.seed;
  if (raw === undefined || raw === null) return null;
  let value;
  if (typeof raw === "number") {
    if (!Number.isInteger(raw)) {
      throw new Error("vm.seed must be an integer");
    }
    if (!Number.isSafeInteger(raw)) {
      throw new Error("vm.seed numeric TOML values must be safe integers; use a quoted string for large u64 seeds");
    }
    value = BigInt(raw);
  } else if (typeof raw === "string") {
    const text = raw.trim();
    if (!text) return null;
    value = BigInt(text);
  } else if (typeof raw === "bigint") {
    value = raw;
  } else {
    throw new Error("vm.seed must be an integer or string");
  }
  if (value < 0n || value > 0xffffffffffffffffn) {
    throw new Error("vm.seed must be within u64 range");
  }
  return value;
}

function segmentKindCode(kind) {
  const value = (kind || "").toString().trim().toLowerCase();
  if (value === "weights") return SEGMENT_KIND_WEIGHTS;
  if (value === "ram") return SEGMENT_KIND_RAM;
  return null;
}

function vmSeedString(vmSeed) {
  return `fbv1:vm:${vmSeed.toString(16).padStart(16, "0")}`;
}

function segmentSeedString(vmSeed, kindCode, slot) {
  return `fbv1:sg:${vmSeed.toString(16).padStart(16, "0")}:${kindCode
    .toString(16)
    .padStart(2, "0")}${slot.toString(16).padStart(2, "0")}`;
}

async function normalizePdaSegments(segments, { vmSeed, authorityPubkey, programId }) {
  const normalized = [];
  for (let i = 0; i < segments.length; i += 1) {
    const seg = segments[i] || {};
    const configuredPubkey = typeof seg.pubkey === "string" ? seg.pubkey : null;
    if (seg.pubkey !== undefined && configuredPubkey === null) {
      throw new Error(`segment ${i + 1} pubkey must be a base58 string when provided`);
    }
    const kindCode = segmentKindCode(seg.kind);
    if (kindCode === null) {
      throw new Error(`segment ${i + 1} has unsupported kind '${seg.kind}' (expected weights|ram)`);
    }
    const slot = Number(seg.slot ?? seg.index ?? i + 1);
    if (!Number.isInteger(slot) || slot < 1 || slot > 15) {
      throw new Error(`segment ${i + 1} has invalid slot ${slot} (expected 1..15)`);
    }
    const expectedWritable = kindCode === SEGMENT_KIND_RAM;
    if (Boolean(seg.writable) !== expectedWritable) {
      const accessMode = expectedWritable ? "writable" : "readonly";
      throw new Error(`segment ${i + 1} (${seg.kind}) must be ${accessMode} in deterministic account mode`);
    }
    const derivedPubkey = await PublicKey.createWithSeed(
      authorityPubkey,
      segmentSeedString(vmSeed, kindCode, slot),
      programId
    );
    if (configuredPubkey && configuredPubkey !== derivedPubkey.toBase58()) {
      throw new Error(
        `segment ${i + 1} pubkey does not match deterministic derived address for vm.seed/authority/slot; remove segment pubkey or fix metadata`
      );
    }
    normalized.push({ pubkey: derivedPubkey.toBase58(), slot, kindCode, writable: expectedWritable });
  }

  if (normalized.length === 0) {
    throw new Error("deterministic execute requires at least one mapped segment");
  }
  normalized.sort((a, b) => a.slot - b.slot);

  for (let i = 0; i < normalized.length; i += 1) {
    if (i > 0 && normalized[i - 1].slot === normalized[i].slot) {
      throw new Error(`duplicate segment slot ${normalized[i].slot} in deterministic account mode`);
    }
    if (normalized[i].slot !== i + 1) {
      throw new Error(
        `deterministic execute requires contiguous slots starting at 1; missing slot ${i + 1} before slot ${normalized[i].slot}`
      );
    }
  }
  if (normalized[0].kindCode !== SEGMENT_KIND_WEIGHTS) {
    throw new Error("deterministic execute requires a weights segment at slot 1");
  }

  return normalized;
}

async function main() {
  const args = parseArgs(process.argv);
  const accountsPath = args.accounts;
  const manifestPath = args.manifest;
  const gatekeeperId = args["gatekeeper-program-id"];
  const threshold = parseInt(args.threshold || "0", 10);
  const outputIndex = parseInt(args["output-index"] || "0", 10);

  if (!accountsPath || !manifestPath || !gatekeeperId) {
    console.error(
      "Usage: node run_gatekeeper.js --manifest <path> --accounts <path> --gatekeeper-program-id <id> [--threshold 0] [--authority-keypair <path>]"
    );
    process.exit(1);
  }

  const accounts = loadToml(accountsPath);
  const manifest = loadToml(manifestPath);

  const rpcUrl = args["rpc-url"] || accounts.cluster?.rpc_url || "http://127.0.0.1:8899";
  const programIdStr = args["program-id"] || accounts.cluster?.program_id;
  const payerPath = args.payer || accounts.cluster?.payer || path.join(process.env.HOME || "", ".config/solana/id.json");
  if (!programIdStr) {
    console.error("Missing program_id in accounts file");
    process.exit(1);
  }

  const payer = loadKeypair(payerPath);
  const connection = new Connection(rpcUrl, "confirmed");
  const programId = new PublicKey(programIdStr);
  const instructions = BigInt(parseInt(args.instructions || "50000", 10));
  const vmSeed = parseVmSeed(accounts.vm || {});
  const authorityPath = resolveAccountsPath(
    accountsPath,
    args["authority-keypair"] || accounts.vm?.authority_keypair
  );
  const authority = authorityPath ? loadKeypair(authorityPath) : payer;
  const authorityPubkey = typeof accounts.vm?.authority === "string" ? accounts.vm.authority : null;
  if (vmSeed !== null && authorityPubkey && authority.publicKey.toBase58() !== authorityPubkey) {
    throw new Error(
      "authority signer pubkey does not match vm.authority; provide matching --authority-keypair or update accounts file"
    );
  }
  const configuredVmPubkey = accounts.vm?.pubkey || null;
  const authorityForDerivation = authorityPubkey ? new PublicKey(authorityPubkey) : authority.publicKey;
  let vmKey;
  if (vmSeed !== null) {
    vmKey = await PublicKey.createWithSeed(authorityForDerivation, vmSeedString(vmSeed), programId);
    if (configuredVmPubkey && configuredVmPubkey !== vmKey.toBase58()) {
      throw new Error(
        "vm.pubkey does not match deterministic derived VM address for vm.seed/authority; remove vm.pubkey or fix metadata"
      );
    }
  } else {
    if (!configuredVmPubkey) {
      console.error("Missing vm.pubkey in accounts file");
      process.exit(1);
    }
    vmKey = new PublicKey(configuredVmPubkey);
  }

  const execKeys = [
    { pubkey: vmSeed !== null ? authority.publicKey : payer.publicKey, isSigner: true, isWritable: false },
    { pubkey: vmKey, isSigner: false, isWritable: true },
  ];

  let execData;
  if (vmSeed !== null) {
    const segments = await normalizePdaSegments(accounts.segments || [], {
      vmSeed,
      authorityPubkey: authorityForDerivation,
      programId,
    });
    if (segments.length > 15) {
      throw new Error("deterministic execute supports at most 15 mapped segments");
    }
    for (const seg of segments) {
      execKeys.push({
        pubkey: new PublicKey(seg.pubkey),
        isSigner: false,
        isWritable: seg.writable,
      });
    }
    execData = Buffer.alloc(1 + 8 + 8 + 1 + 1 + segments.length);
    execData[0] = EXECUTE_V3_OP;
    execData.writeBigUInt64LE(vmSeed, 1);
    execData.writeBigUInt64LE(instructions, 9);
    execData[17] = 0; // flags
    execData[18] = segments.length;
    for (let i = 0; i < segments.length; i += 1) {
      execData[19 + i] = segments[i].kindCode;
    }
  } else {
    const segments = (accounts.segments || []).slice().sort((a, b) => (a.index || 0) - (b.index || 0));
    for (const seg of segments) {
      if (!seg.pubkey) continue;
      execKeys.push({
        pubkey: new PublicKey(seg.pubkey),
        isSigner: false,
        isWritable: !!seg.writable,
      });
    }
    execData = Buffer.alloc(1 + 8);
    execData[0] = EXECUTE_OP;
    execData.writeBigUInt64LE(instructions, 1);
  }
  const execIx = new TransactionInstruction({
    programId,
    keys: execKeys,
    data: execData,
  });

  const controlOffset = manifest.abi?.control_offset ?? 0;
  const gateData = Buffer.alloc(12);
  gateData.writeUInt32LE(controlOffset >>> 0, 0);
  gateData.writeInt32LE(threshold, 4);
  gateData.writeUInt32LE(outputIndex >>> 0, 8);

  const gateIx = new TransactionInstruction({
    programId: new PublicKey(gatekeeperId),
    keys: [
      { pubkey: vmSeed !== null ? authority.publicKey : payer.publicKey, isSigner: true, isWritable: false },
      { pubkey: vmKey, isSigner: false, isWritable: false },
    ],
    data: gateData,
  });

  const tx = new Transaction();
  tx.add(ComputeBudgetProgram.setComputeUnitLimit({ units: 1_400_000 }));
  tx.add(execIx);
  tx.add(gateIx);

  console.log("Sending execute + gatekeeper tx...");
  const signers = [payer];
  if (authority.publicKey.toBase58() !== payer.publicKey.toBase58()) {
    signers.push(authority);
  }
  await sendAndConfirmTransaction(connection, tx, signers);
  console.log("Gatekeeper passed.");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
