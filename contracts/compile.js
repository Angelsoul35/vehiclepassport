// Compiles contracts/src/VehicleRegistry.sol into
// contracts/artifacts/VehicleRegistry.json using the pinned solc-js compiler.
// No native toolchain required.
const fs = require("fs");
const path = require("path");
const solc = require("solc");

const SRC = path.join(__dirname, "src", "VehicleRegistry.sol");
const OUT = path.join(__dirname, "artifacts", "VehicleRegistry.json");
const CONTRACT = "VehicleRegistry";

const input = {
  language: "Solidity",
  sources: { "VehicleRegistry.sol": { content: fs.readFileSync(SRC, "utf8") } },
  settings: {
    optimizer: { enabled: true, runs: 200 },
    evmVersion: "cancun",
    outputSelection: { "*": { "*": ["abi", "evm.bytecode.object"] } },
  },
};

const output = JSON.parse(solc.compile(JSON.stringify(input)));
const errors = (output.errors || []).filter((e) => e.severity === "error");
if (errors.length) {
  console.error(errors.map((e) => e.formattedMessage).join("\n"));
  process.exit(1);
}
const c = output.contracts["VehicleRegistry.sol"][CONTRACT];
const artifact = {
  contractName: CONTRACT,
  solcVersion: solc.version(),
  abi: c.abi,
  bytecode: "0x" + c.evm.bytecode.object,
};
fs.mkdirSync(path.dirname(OUT), { recursive: true });
fs.writeFileSync(OUT, JSON.stringify(artifact, null, 2) + "\n");
console.log("Wrote", path.relative(path.join(__dirname, ".."), OUT), "with solc", solc.version());
