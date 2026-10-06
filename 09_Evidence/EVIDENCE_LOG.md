# Evidence Log - ChainClaim (DDT CA1)

| ID | File | What it proves | Criterion 2 area |
|---|---|---|---|
| E00a | E00a_ganache_running.png | Ganache v7 running, chain ID 1337, 10 funded accounts | Environment |
| E00b | E00b_remix_connected.png | Remix connected to Ganache via External HTTP Provider | Environment |
| E00c | E00c_remixai_copilot_disabled.png | RemixAI Copilot switched off | Academic integrity |
| E02 | E02_compile_success.png | ChainClaim.sol compiles (solc 0.8.24, EVM shanghai) | Development |
| E03 | E03_deploy_remix.png | Contract deployed from Remix with assessor address | Deployment |
| E04 | E04_deploy_ganache.png | Deployment transaction visible on Ganache | Deployment |
| E05 | E05_flow_policy_claim.png | fundPool, buyPolicy, submitClaim with evidence hash | Execution / transactions |
| E06 | E06_ecdsa_signature.png | EIP-712 digest, r, s, v, recovered signer = assessor | Execution / cryptography |
| E07 | E07_payout.png | payClaim, balance before/after, status Paid | Execution / transactions |
| E08 | E08_security_tests.png | 13 negative/security tests revert with correct reasons | Testing |
| E09 | E09_summary_gas.png | 13/13 summary and gas report | Testing |
| E10a | E10a_run_all_start.png | Shell script: tool check, Ganache start, contract check | Shell automation |
| E10b | E10b_run_all_results.png | Shell script: tests run, "All checks passed" | Shell automation |

All screenshots were taken by me from my own machine. No figures were edited or invented.
