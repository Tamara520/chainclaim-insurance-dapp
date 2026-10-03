#!/usr/bin/env bash
# ==================================================================
# ChainClaim - one-command test runner
# Author : Tsolmon Jargalsaikhan (2024520) - CCT College Dublin, DDT CA1
#
# 1. Checks the tools (Python, web3, Node, Ganache)
# 2. Starts Ganache (chain ID 1337) if it is not already running
# 3. Deploys ChainClaim if no contract exists at the saved address
# 4. Runs the full interaction + security test script
# 5. Saves the output and the gas report to 03_Testing/
#
# Usage (from the project folder):
#     conda activate chainclaim
#     ./04_Scripts/run_all.sh
# ==================================================================
set -euo pipefail

cd "$(dirname "$0")/.."
RPC="http://127.0.0.1:8545"
ADDRESS_FILE="04_Scripts/contract_address.txt"
OUTPUT="03_Testing/run_output.txt"

step() { printf "\n\033[1;34m==> %s\033[0m\n" "$1"; }
ok()   { printf "  \033[0;32m✔\033[0m %s\n" "$1"; }
fail() { printf "  \033[0;31m✘ %s\033[0m\n" "$1"; exit 1; }

rpc() {
  curl -s -X POST -H "Content-Type: application/json" \
       --data "{\"jsonrpc\":\"2.0\",\"method\":\"$1\",\"params\":$2,\"id\":1}" "$RPC"
}

# ------------------------------------------------------------------
step "1/5  Checking tools"
command -v python >/dev/null || fail "python not found (run: conda activate chainclaim)"
python -c "import web3, solcx" 2>/dev/null || fail "web3 / py-solc-x missing (run: conda activate chainclaim)"
command -v ganache >/dev/null || fail "ganache not found (run: sudo npm install -g ganache)"
ok "Python $(python -c 'import platform;print(platform.python_version())')"
ok "web3 $(python -c 'import web3;print(web3.__version__)')"
ok "Node $(node --version)"

# ------------------------------------------------------------------
step "2/5  Starting Ganache"
if rpc eth_chainId "[]" | grep -q '"result"'; then
  ok "Ganache already running on $RPC"
else
  nohup ganache --deterministic --port 8545 > ganache.log 2>&1 &
  for _ in $(seq 1 30); do
    sleep 1
    rpc eth_chainId "[]" | grep -q '"result"' && break
  done
  rpc eth_chainId "[]" | grep -q '"result"' || fail "Ganache did not start (see ganache.log)"
  ok "Ganache started on $RPC"
fi
ok "Chain ID: $(( $(rpc eth_chainId '[]' | sed -E 's/.*"result":"([^"]+)".*/\1/') ))"

# ------------------------------------------------------------------
step "3/5  Checking the ChainClaim contract"
ADDRESS="$(cat "$ADDRESS_FILE" 2>/dev/null || true)"
CODE="$(rpc eth_getCode "[\"$ADDRESS\",\"latest\"]" | sed -E 's/.*"result":"([^"]*)".*/\1/')"
if [[ -n "$ADDRESS" && "$CODE" != "0x" && "$CODE" == 0x* ]]; then
  ok "Contract found at $ADDRESS"
else
  echo "  No contract at saved address - deploying a fresh copy"
  python 04_Scripts/deploy.py
  ok "Contract deployed at $(cat "$ADDRESS_FILE")"
fi

# ------------------------------------------------------------------
step "4/5  Running interaction and security tests"
python 04_Scripts/interact.py | tee "$OUTPUT"

# ------------------------------------------------------------------
step "5/5  Results"
PASSED="$(grep -Eo 'tests passed: [0-9]+ / [0-9]+' "$OUTPUT" | tail -1)"
ok "Security $PASSED"
ok "Full output : $OUTPUT"
ok "Gas report  : 03_Testing/gas_report.csv"
grep -q "FAIL" "$OUTPUT" && fail "At least one test failed" || ok "All checks passed"
