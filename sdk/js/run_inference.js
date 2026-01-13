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

const MMU_VM_HEADER_SIZE = 545;
const EXECUTE_OP = 2;

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

function readU32LE(buf, offset) {
  return buf.readUInt32LE(offset);
}

function decodeI32(buf) {
  const out = [];
  for (let i = 0; i + 4 <= buf.length; i += 4) {
    out.push(buf.readInt32LE(i));
  }
  return out;
}

async function main() {
  const args = parseArgs(process.argv);
  const accountsPath = args.accounts;
  const manifestPath = args.manifest;
  if (!accountsPath || !manifestPath) {
    console.error("Usage: node run_inference.js --manifest <path> --accounts <path> [--instructions 50000]");
    process.exit(1);
  }

  const accounts = loadToml(accountsPath);
  const manifest = loadToml(manifestPath);

  const rpcUrl = args["rpc-url"] || accounts.cluster?.rpc_url || "http://127.0.0.1:8899";
  const programIdStr = args["program-id"] || accounts.cluster?.program_id;
  const payerPath = args.payer || accounts.cluster?.payer || path.join(process.env.HOME || "", ".config/solana/id.json");
  const vmPubkey = accounts.vm?.pubkey;
  if (!programIdStr || !vmPubkey) {
    console.error("Missing program_id or vm.pubkey in accounts file");
    process.exit(1);
  }

  const payer = loadKeypair(payerPath);
  const connection = new Connection(rpcUrl, "confirmed");
  const programId = new PublicKey(programIdStr);
  const instructions = BigInt(parseInt(args.instructions || "50000", 10));

  const segments = (accounts.segments || []).slice().sort((a, b) => (a.index || 0) - (b.index || 0));
  const keys = [
    { pubkey: payer.publicKey, isSigner: true, isWritable: false },
    { pubkey: new PublicKey(vmPubkey), isSigner: false, isWritable: true },
  ];
  for (const seg of segments) {
    if (!seg.pubkey) continue;
    keys.push({
      pubkey: new PublicKey(seg.pubkey),
      isSigner: false,
      isWritable: !!seg.writable,
    });
  }

  const data = Buffer.alloc(1 + 8);
  data[0] = EXECUTE_OP;
  data.writeBigUInt64LE(instructions, 1);

  const execIx = new TransactionInstruction({
    programId,
    keys,
    data,
  });

  const tx = new Transaction();
  tx.add(ComputeBudgetProgram.setComputeUnitLimit({ units: 1_400_000 }));
  tx.add(execIx);

  console.log("Sending execute tx...");
  await sendAndConfirmTransaction(connection, tx, [payer]);

  const accountInfo = await connection.getAccountInfo(new PublicKey(vmPubkey));
  if (!accountInfo) {
    throw new Error("VM account not found");
  }
  const scratch = accountInfo.data.slice(MMU_VM_HEADER_SIZE);
  const controlOffset = manifest.abi?.control_offset ?? 0;
  const outputOffset = manifest.abi?.output_offset ?? 0;
  const outputMax = manifest.abi?.output_max ?? 0;

  const status = readU32LE(scratch, controlOffset + 12);
  let outputLen = readU32LE(scratch, controlOffset + 28);
  if (outputLen === 0 && args["use-max"]) {
    outputLen = outputMax;
  }
  const output = scratch.slice(outputOffset, outputOffset + outputLen);

  console.log("Status:", status);
  if (output.length) {
    console.log("Output (i32):", decodeI32(output));
  } else {
    console.log("Output: <empty>");
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
