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

async function main() {
  const args = parseArgs(process.argv);
  const accountsPath = args.accounts;
  const manifestPath = args.manifest;
  const gatekeeperId = args["gatekeeper-program-id"];
  const threshold = parseInt(args.threshold || "0", 10);
  const outputIndex = parseInt(args["output-index"] || "0", 10);

  if (!accountsPath || !manifestPath || !gatekeeperId) {
    console.error(
      "Usage: node run_gatekeeper.js --manifest <path> --accounts <path> --gatekeeper-program-id <id> [--threshold 0]"
    );
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
  const vmKey = new PublicKey(vmPubkey);
  const instructions = BigInt(parseInt(args.instructions || "50000", 10));

  const segments = (accounts.segments || []).slice().sort((a, b) => (a.index || 0) - (b.index || 0));
  const execKeys = [
    { pubkey: payer.publicKey, isSigner: true, isWritable: false },
    { pubkey: vmKey, isSigner: false, isWritable: true },
  ];
  for (const seg of segments) {
    if (!seg.pubkey) continue;
    execKeys.push({
      pubkey: new PublicKey(seg.pubkey),
      isSigner: false,
      isWritable: !!seg.writable,
    });
  }

  const execData = Buffer.alloc(1 + 8);
  execData[0] = EXECUTE_OP;
  execData.writeBigUInt64LE(instructions, 1);
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
      { pubkey: payer.publicKey, isSigner: true, isWritable: false },
      { pubkey: vmKey, isSigner: false, isWritable: false },
    ],
    data: gateData,
  });

  const tx = new Transaction();
  tx.add(ComputeBudgetProgram.setComputeUnitLimit({ units: 1_400_000 }));
  tx.add(execIx);
  tx.add(gateIx);

  console.log("Sending execute + gatekeeper tx...");
  await sendAndConfirmTransaction(connection, tx, [payer]);
  console.log("Gatekeeper passed.");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
