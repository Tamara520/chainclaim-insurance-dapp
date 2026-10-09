# ChainClaim: A Blockchain-Based Insurance Claims Settlement DApp

**Module:** Distributed Digital Transactions (DDT) - CA1
**Student:** Tsolmon Jargalsaikhan (2024520) - CCT College Dublin, BSc Computing in IT (Year 3)
**Lecturer:** Dr. Muhammad Iqbal

ChainClaim places a Solidity smart contract between the **policyholder (sender)** and the
**insurer (receiver)**. The contract holds premiums and the claims pool in escrow, records each
claim with a Keccak-256 evidence hash, and releases a payout only after an **independent assessor**
approves the claim with an **EIP-712 / ECDSA (secp256k1)** signature that is verified on-chain.

## Roles

| Role | Ganache account | What it does |
|---|---|---|
| Insurer (receiver) | 0 | Deploys the contract, funds the claims pool, can pause/unpause |
| Policyholder (sender) | 1 | Buys a policy (0.01 ETH), submits claims, pulls the payout |
| Assessor | 2 | Signs approve/reject decisions off-chain (0 gas) |
| Attacker (tests only) | 3 | Used to prove that unauthorised actions revert |

## Claim lifecycle

Submitted -> Approved -> Paid, or Submitted -> Rejected

## Security features

- EIP-712 typed-data signatures recovered with `ecrecover`; signer must equal the assessor
- Replay protection: nonce + deadline; EIP-2 low-s check against signature malleability
- Duplicate-claim protection: each evidence hash can be used only once
- Only the evidence **hash** is stored on-chain (no personal data - GDPR friendly)
- Checks-Effects-Interactions, `nonReentrant` guard and claimant-callable payout
- Cover limit (`MAX_COVER = 5 ETH`), insurer-only `fundPool`, `pause` circuit breaker
- Plain ETH transfers to the contract are rejected

## Tools

Solidity 0.8.24 (EVM shanghai) - Remix IDE - Ganache v7 (chain ID 1337) -
Python 3.11 + web3.py 8 + eth-account + py-solc-x - Bash shell script

## Project structure

| Path | Content |
|---|---|
| `02_Smart_Contract/ChainClaim.sol` | Smart contract (middle layer) |
| `04_Scripts/deploy.py` | Compiles and deploys the contract with web3.py |
| `04_Scripts/interact.py` | Full claim flow, EIP-712 signing and 13 security tests |
| `04_Scripts/run_all.sh` | One-command runner: Ganache -> deploy -> tests |
| `03_Testing/run_output.txt` | Latest test output |
| `03_Testing/gas_report.csv` | Gas used per transaction |
| `09_Evidence/` | Screenshots E00a-E10b (see `EVIDENCE_LOG.md`) |

## How to run

    conda create -n chainclaim python=3.11 -y
    conda activate chainclaim
    pip install web3 py-solc-x
    sudo npm install -g ganache
    ./04_Scripts/run_all.sh

The script starts Ganache if needed, deploys ChainClaim if no contract exists at the saved
address, runs the full flow and the 13 negative/security tests, and saves the output and gas report.

## Results (from my own runs)

- Negative/security tests passed: **13 / 13**
- Gas: submitClaim ~150k, assessClaim ~103k, payClaim ~47k, fundPool ~23k (exact values in
  `03_Testing/gas_report.csv`; they vary by a few gas between runs)
- Assessor signing cost: **0 gas** (signed off-chain)

## Warning

The private keys in `interact.py` are the public Ganache `--deterministic` test keys.
They must never be used on a real network.


