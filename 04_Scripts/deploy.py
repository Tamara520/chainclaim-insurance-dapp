"""
ChainClaim - deploy script (web3.py + py-solc-x + Ganache)
Author : Tsolmon Jargalsaikhan (2024520) - CCT College Dublin, DDT CA1

Compiles 02_Smart_Contract/ChainClaim.sol (Solidity 0.8.24, EVM shanghai),
deploys it from the insurer (Ganache account 0) with the independent
assessor (Ganache account 2) and saves the contract address to
04_Scripts/contract_address.txt.
"""

import json
from pathlib import Path

import solcx
from web3 import Web3

ROOT = Path(__file__).resolve().parent.parent
CONTRACT_SOL = ROOT / "02_Smart_Contract" / "ChainClaim.sol"
ABI_FILE = ROOT / "04_Scripts" / "ChainClaim.abi.json"
ADDRESS_FILE = ROOT / "04_Scripts" / "contract_address.txt"

w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:8545"))
assert w3.is_connected(), "Ganache is not running on 127.0.0.1:8545"
insurer, assessor = w3.eth.accounts[0], w3.eth.accounts[2]

solcx.install_solc("0.8.24")
compiled = solcx.compile_files(
    [str(CONTRACT_SOL)],
    output_values=["abi", "bin"],
    solc_version="0.8.24",
    evm_version="shanghai",
)
artifact = next(v for k, v in compiled.items() if k.endswith(":ChainClaim"))
ABI_FILE.write_text(json.dumps(artifact["abi"], indent=2))

ChainClaim = w3.eth.contract(abi=artifact["abi"], bytecode=artifact["bin"])
tx_hash = ChainClaim.constructor(assessor).transact({"from": insurer})
receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

ADDRESS_FILE.write_text(receipt.contractAddress + "\n")
print(f"  Compiler         : solc 0.8.24 (EVM shanghai)")
print(f"  Deployed by      : {insurer} (insurer)")
print(f"  Assessor         : {assessor}")
print(f"  Contract address : {receipt.contractAddress}")
print(f"  Transaction      : {Web3.to_hex(tx_hash)}")
print(f"  Block / gas used : {receipt.blockNumber} / {receipt.gasUsed}")
