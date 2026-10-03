"""
ChainClaim - Python interaction script (web3.py + Ganache)
Author : Tsolmon Jargalsaikhan (2024520) - CCT College Dublin, DDT CA1

What this script demonstrates
  1. Sender -> blockchain -> receiver flow on the deployed ChainClaim contract
       insurer funds pool -> policyholder buys policy -> policyholder submits claim
       -> assessor signs decision OFF-CHAIN (EIP-712 + ECDSA secp256k1, 0 gas)
       -> signature verified ON-CHAIN (ecrecover) -> claimant is paid
  2. Negative / security tests that must revert
  3. A gas report saved to 03_Testing/gas_report.csv

Run (Ganache must be running on 127.0.0.1:8545):
    conda activate chainclaim
    python 04_Scripts/interact.py
"""

import csv
import json
import time
from pathlib import Path

from eth_account import Account
from eth_account.messages import encode_typed_data
from web3 import Web3

# ------------------------------------------------------------------
# 0. CONFIGURATION
# ------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
CONTRACT_SOL = ROOT / "02_Smart_Contract" / "ChainClaim.sol"
ABI_FILE = ROOT / "04_Scripts" / "ChainClaim.abi.json"
ADDRESS_FILE = ROOT / "04_Scripts" / "contract_address.txt"
GAS_REPORT = ROOT / "03_Testing" / "gas_report.csv"

RPC_URL = "http://127.0.0.1:8545"

# Ganache --deterministic test accounts (public test keys, NEVER use on a real network)
ASSESSOR_KEY = "0x6370fd033278c143179d81c5526140625662b8daa446c22ee2d73db3707e620c"  # account 2
ATTACKER_KEY = "0x646f1ce2fdad0e6deeeb5c7e8e5543bdde65e86029e2fd9fc169899c440a7913"  # account 3

STATUS = ["Submitted", "Approved", "Rejected", "Paid"]
gas_rows = []


def line(title=""):
    print("\n" + "=" * 70)
    if title:
        print(title)
        print("=" * 70)


def load_abi():
    """Load the ABI from file, or compile ChainClaim.sol once with py-solc-x."""
    if ABI_FILE.exists():
        return json.loads(ABI_FILE.read_text())
    import solcx
    solcx.install_solc("0.8.24")
    out = solcx.compile_files(
        [str(CONTRACT_SOL)],
        output_values=["abi"],
        solc_version="0.8.24",
        evm_version="shanghai",
    )
    abi = next(v["abi"] for k, v in out.items() if k.endswith(":ChainClaim"))
    ABI_FILE.write_text(json.dumps(abi, indent=2))
    return abi


def send(label, fn, sender, value=0):
    """Send a transaction, wait for the receipt and record gas used."""
    tx_hash = fn.transact({"from": sender, "value": value})
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    gas_rows.append((label, receipt.gasUsed, receipt.blockNumber, Web3.to_hex(tx_hash)))
    print(f"  OK  {label:<34} gas={receipt.gasUsed:<7} block={receipt.blockNumber} "
          f"tx={Web3.to_hex(tx_hash)[:20]}...")
    return receipt


def expect_revert(label, action, expected_reason):
    """Run an action that MUST fail and check the revert reason."""
    try:
        action()
        print(f"  FAIL {label:<40} (transaction was NOT rejected)")
        return False
    except Exception as err:  # web3 raises ContractLogicError with the reason
        msg = str(err)
        passed = expected_reason in msg
        mark = "PASS" if passed else "FAIL"
        print(f"  {mark} {label:<40} -> reverted: \"{expected_reason}\"")
        return passed


def sign_assessment(private_key, claim_id, approved, nonce, deadline):
    """Assessor signs the decision OFF-CHAIN as EIP-712 typed data (no gas)."""
    typed_data = {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "Assessment": [
                {"name": "claimId", "type": "uint256"},
                {"name": "approved", "type": "bool"},
                {"name": "nonce", "type": "uint256"},
                {"name": "deadline", "type": "uint256"},
            ],
        },
        "primaryType": "Assessment",
        "domain": {
            "name": "ChainClaim",
            "version": "1",
            "chainId": w3.eth.chain_id,
            "verifyingContract": contract.address,
        },
        "message": {
            "claimId": claim_id,
            "approved": approved,
            "nonce": nonce,
            "deadline": deadline,
        },
    }
    message = encode_typed_data(full_message=typed_data)
    signed = Account.sign_message(message, private_key)
    return message, signed


# ------------------------------------------------------------------
# 1. CONNECT TO GANACHE AND THE DEPLOYED CONTRACT
# ------------------------------------------------------------------
line("1. CONNECT TO GANACHE")
w3 = Web3(Web3.HTTPProvider(RPC_URL))
assert w3.is_connected(), "Ganache is not running on 127.0.0.1:8545"

accounts = w3.eth.accounts
INSURER, HOLDER, ASSESSOR, ATTACKER = accounts[0], accounts[1], accounts[2], accounts[3]
print(f"  Chain ID      : {w3.eth.chain_id}")
print(f"  Latest block  : {w3.eth.block_number}")
print(f"  Insurer  (receiver) : {INSURER}")
print(f"  Policyholder (sender): {HOLDER}")
print(f"  Assessor            : {ASSESSOR}")
print(f"  Attacker (tests)    : {ATTACKER}")

address = Web3.to_checksum_address(ADDRESS_FILE.read_text().strip())
contract = w3.eth.contract(address=address, abi=load_abi())
print(f"  ChainClaim contract : {contract.address}")
print(f"  Assessor on-chain   : {contract.functions.assessor().call()}")
assert contract.functions.assessor().call() == ASSESSOR, "Assessor address mismatch"

# ------------------------------------------------------------------
# 2. NORMAL FLOW: SENDER -> BLOCKCHAIN -> RECEIVER
# ------------------------------------------------------------------
line("2. NORMAL CLAIM FLOW")
premium = contract.functions.POLICY_PREMIUM().call()

send("fundPool (insurer, 10 ETH)", contract.functions.fundPool(), INSURER, w3.to_wei(10, "ether"))

if not contract.functions.hasPolicy(HOLDER).call():
    send("buyPolicy (holder, 0.01 ETH)", contract.functions.buyPolicy(), HOLDER, premium)
else:
    print("  --  buyPolicy skipped (holder already has a policy)")

run_id = int(time.time())
evidence_text = f"accident-report-{run_id}.pdf"
evidence_hash = Web3.keccak(text=evidence_text)
print(f"  Evidence file       : {evidence_text}")
print(f"  Keccak-256 hash     : {Web3.to_hex(evidence_hash)}  (only the hash goes on-chain)")

claim_id = contract.functions.claimCount().call()
claim_amount = w3.to_wei(4, "ether")
send("submitClaim (holder, 4 ETH)", contract.functions.submitClaim(claim_amount, evidence_hash), HOLDER)
print(f"  Claim #{claim_id} status    : {STATUS[contract.functions.getClaim(claim_id).call()[3]]}")

# ------------------------------------------------------------------
# 3. ASSESSOR SIGNS OFF-CHAIN, CONTRACT VERIFIES ON-CHAIN
# ------------------------------------------------------------------
line("3. EIP-712 + ECDSA ASSESSOR SIGNATURE")
nonce = run_id
deadline = w3.eth.get_block("latest").timestamp + 3600
msg, signed = sign_assessment(ASSESSOR_KEY, claim_id, True, nonce, deadline)

offchain_signer = Account.recover_message(msg, signature=signed.signature)
onchain_digest = contract.functions.getAssessmentDigest(claim_id, True, nonce, deadline).call()
print(f"  EIP-712 digest (contract): 0x{onchain_digest.hex()}")
print(f"  Signature r      : {hex(signed.r)}")
print(f"  Signature s      : {hex(signed.s)}")
print(f"  Signature v      : {signed.v}")
print(f"  Recovered signer : {offchain_signer}  (matches assessor: {offchain_signer == ASSESSOR})")
print("  Gas used to sign : 0 (signed off-chain)")

send("assessClaim (relayed by holder)",
     contract.functions.assessClaim(claim_id, True, nonce, deadline, signed.signature), HOLDER)
print(f"  Claim #{claim_id} status    : {STATUS[contract.functions.getClaim(claim_id).call()[3]]}")

# ------------------------------------------------------------------
# 4. PAYOUT TO THE CLAIMANT
# ------------------------------------------------------------------
line("4. PAYOUT")
before = w3.eth.get_balance(HOLDER)
receipt = send("payClaim (holder pulls payout)", contract.functions.payClaim(claim_id), HOLDER)
after = w3.eth.get_balance(HOLDER)
gas_cost = receipt.gasUsed * receipt.effectiveGasPrice
print(f"  Holder balance before : {w3.from_wei(before, 'ether')} ETH")
print(f"  Holder balance after  : {w3.from_wei(after, 'ether')} ETH")
print(f"  Received (after gas)  : {w3.from_wei(after - before + gas_cost, 'ether')} ETH")
print(f"  Claim #{claim_id} status    : {STATUS[contract.functions.getClaim(claim_id).call()[3]]}")
print(f"  Contract balance      : {w3.from_wei(contract.functions.getContractBalance().call(), 'ether')} ETH")

# ------------------------------------------------------------------
# 5. NEGATIVE AND SECURITY TESTS (all must revert)
# ------------------------------------------------------------------
line("5. NEGATIVE AND SECURITY TESTS")
results = []
fresh_hash = Web3.keccak(text=f"report-b-{run_id}.pdf")

results.append(expect_revert(
    "Duplicate evidence (reused hash)",
    lambda: contract.functions.submitClaim(1, evidence_hash).transact({"from": HOLDER}),
    "Evidence already used"))

results.append(expect_revert(
    "Claim without a policy (attacker)",
    lambda: contract.functions.submitClaim(1, fresh_hash).transact({"from": ATTACKER}),
    "Active policy required"))

results.append(expect_revert(
    "Claim above cover limit (6 ETH)",
    lambda: contract.functions.submitClaim(w3.to_wei(6, "ether"), fresh_hash).transact({"from": HOLDER}),
    "Exceeds cover limit"))

results.append(expect_revert(
    "Pay the same claim twice",
    lambda: contract.functions.payClaim(claim_id).transact({"from": HOLDER}),
    "Claim not approved"))

# second claim used for signature attacks
claim2 = contract.functions.claimCount().call()
send("submitClaim #2 (holder, 1 ETH)",
     contract.functions.submitClaim(w3.to_wei(1, "ether"), fresh_hash), HOLDER)

_, forged = sign_assessment(ATTACKER_KEY, claim2, True, nonce + 1, deadline)
results.append(expect_revert(
    "Forged signature (attacker key)",
    lambda: contract.functions.assessClaim(claim2, True, nonce + 1, deadline, forged.signature)
    .transact({"from": HOLDER}),
    "Invalid assessor signature"))

_, rejected_sig = sign_assessment(ASSESSOR_KEY, claim2, False, nonce + 2, deadline)
results.append(expect_revert(
    "Tampered decision (false -> true)",
    lambda: contract.functions.assessClaim(claim2, True, nonce + 2, deadline, rejected_sig.signature)
    .transact({"from": HOLDER}),
    "Invalid assessor signature"))

_, replay_sig = sign_assessment(ASSESSOR_KEY, claim2, True, nonce, deadline)
results.append(expect_revert(
    "Replay of a used nonce",
    lambda: contract.functions.assessClaim(claim2, True, nonce, deadline, replay_sig.signature)
    .transact({"from": HOLDER}),
    "Assessment nonce already used"))

_, expired_sig = sign_assessment(ASSESSOR_KEY, claim2, True, nonce + 3, 1)
results.append(expect_revert(
    "Expired signature (deadline passed)",
    lambda: contract.functions.assessClaim(claim2, True, nonce + 3, 1, expired_sig.signature)
    .transact({"from": HOLDER}),
    "Signature expired"))

results.append(expect_revert(
    "Unauthorised payout (attacker)",
    lambda: contract.functions.payClaim(claim2).transact({"from": ATTACKER}),
    "Not authorised"))

results.append(expect_revert(
    "Attacker funds pool (only insurer)",
    lambda: contract.functions.fundPool().transact({"from": ATTACKER, "value": 1}),
    "Only insurer"))

results.append(expect_revert(
    "Plain ETH transfer to contract",
    lambda: w3.eth.send_transaction({"from": ATTACKER, "to": contract.address, "value": 1}),
    "Use fundPool or buyPolicy"))

# assessor rejects claim #2 (valid signature, decision = false)
_, reject_ok = sign_assessment(ASSESSOR_KEY, claim2, False, nonce + 4, deadline)
send("assessClaim #2 = REJECTED",
     contract.functions.assessClaim(claim2, False, nonce + 4, deadline, reject_ok.signature), HOLDER)
print(f"  Claim #{claim2} status    : {STATUS[contract.functions.getClaim(claim2).call()[3]]}")

# circuit breaker
results.append(expect_revert(
    "Attacker pauses contract",
    lambda: contract.functions.pause().transact({"from": ATTACKER}),
    "Only insurer"))
send("pause (insurer)", contract.functions.pause(), INSURER)
results.append(expect_revert(
    "Submit claim while paused",
    lambda: contract.functions.submitClaim(1, Web3.keccak(text=f"c-{run_id}")).transact({"from": HOLDER}),
    "Contract is paused"))
send("unpause (insurer)", contract.functions.unpause(), INSURER)

# ------------------------------------------------------------------
# 6. SUMMARY AND GAS REPORT
# ------------------------------------------------------------------
line("6. SUMMARY")
print(f"  Negative/security tests passed: {sum(results)} / {len(results)}")

GAS_REPORT.parent.mkdir(exist_ok=True)
with GAS_REPORT.open("w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["function", "gas_used", "block", "tx_hash"])
    writer.writerows(gas_rows)
print(f"  Gas report saved to: {GAS_REPORT.relative_to(ROOT)}")
for label, gas, _, _ in gas_rows:
    print(f"    {label:<34} {gas:>8}")
