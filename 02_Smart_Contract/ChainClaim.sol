// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title  ChainClaim - Blockchain-Based Insurance Claims Settlement DApp
/// @author Tsolmon Jargalsaikhan (2024520) - CCT College Dublin, DDT CA1
/// @notice The smart contract is the middle layer between the policyholder
///         (sender) and the insurer (receiver). It holds premiums and the
///         claims pool in escrow, records every claim and pays out only after
///         a valid, signed assessment.
/// @dev    Assessor approval uses EIP-712 typed data signed off-chain with
///         ECDSA (secp256k1) and verified on-chain with ecrecover.
///         Compile with EVM version "shanghai" for Ganache v7.
contract ChainClaim {

    // ============================================================
    // 1. CLAIM STATE MACHINE
    //    Submitted -> Approved -> Paid
    //    Submitted -> Rejected
    // ============================================================

    enum ClaimStatus {
        Submitted,
        Approved,
        Rejected,
        Paid
    }

    // ============================================================
    // 2. CLAIM STRUCTURE
    // ============================================================

    struct Claim {
        address claimant;       // policyholder who submitted the claim (sender)
        uint256 amount;         // requested payout in wei
        bytes32 evidenceHash;   // Keccak-256 hash of the off-chain evidence file
        ClaimStatus status;     // current position in the state machine
        uint256 nonce;          // nonce of the assessor signature used
        uint256 submittedAt;    // block timestamp of submission
    }

    // ============================================================
    // 3. STATE VARIABLES
    // ============================================================

    address public immutable insurer;    // receiver, deploys the contract
    address public immutable assessor;   // independent loss assessor

    uint256 public claimCount;

    uint256 public constant POLICY_PREMIUM = 0.01 ether;
    uint256 public constant MAX_COVER = 5 ether;

    bool public paused;

    uint256 private _locked = 1;

    // ============================================================
    // 4. MAPPINGS
    // ============================================================

    mapping(uint256 => Claim) public claims;           // claimId -> Claim
    mapping(address => bool) public hasPolicy;         // holder -> active policy
    mapping(bytes32 => bool) public usedEvidence;      // blocks duplicate claims
    mapping(uint256 => bool) public usedAssessmentNonce; // blocks signature replay

    // ============================================================
    // 5. EIP-712 DOMAIN
    // ============================================================

    bytes32 public immutable DOMAIN_SEPARATOR;

    bytes32 public constant ASSESSMENT_TYPEHASH =
        keccak256(
            "Assessment(uint256 claimId,bool approved,uint256 nonce,uint256 deadline)"
        );

    // ============================================================
    // 6. EVENTS (immutable audit trail)
    // ============================================================

    event PoolFunded(address indexed insurer, uint256 amount);
    event PolicyPurchased(address indexed holder, uint256 premium);
    event ClaimSubmitted(
        uint256 indexed claimId,
        address indexed claimant,
        uint256 amount,
        bytes32 evidenceHash
    );
    event ClaimAssessed(uint256 indexed claimId, bool approved, uint256 nonce);
    event ClaimPaid(uint256 indexed claimId, address indexed claimant, uint256 amount);
    event ContractPaused(address indexed insurer);
    event ContractUnpaused(address indexed insurer);

    // ============================================================
    // 7. MODIFIERS
    // ============================================================

    modifier onlyInsurer() {
        require(msg.sender == insurer, "Only insurer");
        _;
    }

    modifier whenNotPaused() {
        require(!paused, "Contract is paused");
        _;
    }

    modifier nonReentrant() {
        require(_locked == 1, "Reentrancy blocked");
        _locked = 2;
        _;
        _locked = 1;
    }

    // ============================================================
    // 8. CONSTRUCTOR
    // ============================================================

    constructor(address _assessor) {
        require(_assessor != address(0), "Invalid assessor");
        require(_assessor != msg.sender, "Assessor must be independent");

        insurer = msg.sender;
        assessor = _assessor;

        DOMAIN_SEPARATOR = keccak256(
            abi.encode(
                keccak256(
                    "EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
                ),
                keccak256(bytes("ChainClaim")),
                keccak256(bytes("1")),
                block.chainid,
                address(this)
            )
        );
    }

    // ============================================================
    // 9. RECEIVE - plain ETH transfers are rejected
    // ============================================================

    receive() external payable {
        revert("Use fundPool or buyPolicy");
    }

    // ============================================================
    // 10. INSURER FUNDS THE CLAIMS POOL
    // ============================================================

    function fundPool() external payable onlyInsurer {
        require(msg.value > 0, "No funds sent");
        emit PoolFunded(msg.sender, msg.value);
    }

    // ============================================================
    // 11. POLICYHOLDER BUYS A POLICY (sender pays premium)
    // ============================================================

    function buyPolicy() external payable whenNotPaused {
        require(msg.sender != insurer && msg.sender != assessor, "Role cannot buy policy");
        require(!hasPolicy[msg.sender], "Policy already exists");
        require(msg.value == POLICY_PREMIUM, "Incorrect premium");

        hasPolicy[msg.sender] = true;

        emit PolicyPurchased(msg.sender, msg.value);
    }

    // ============================================================
    // 12. POLICYHOLDER SUBMITS A CLAIM
    //     Only the evidence HASH is stored on-chain (GDPR friendly).
    // ============================================================

    function submitClaim(uint256 amount, bytes32 evidenceHash) external whenNotPaused {
        require(hasPolicy[msg.sender], "Active policy required");
        require(amount > 0, "Claim amount must be greater than zero");
        require(amount <= MAX_COVER, "Exceeds cover limit");
        require(evidenceHash != bytes32(0), "Evidence hash required");
        require(!usedEvidence[evidenceHash], "Evidence already used");
        require(amount <= address(this).balance, "Insufficient escrow balance");

        uint256 claimId = claimCount;
        claimCount += 1;

        usedEvidence[evidenceHash] = true;

        claims[claimId] = Claim({
            claimant: msg.sender,
            amount: amount,
            evidenceHash: evidenceHash,
            status: ClaimStatus.Submitted,
            nonce: 0,
            submittedAt: block.timestamp
        });

        emit ClaimSubmitted(claimId, msg.sender, amount, evidenceHash);
    }

    // ============================================================
    // 13. ASSESS CLAIM WITH AN EIP-712 + ECDSA SIGNATURE
    //     The assessor signs off-chain (no gas). Anyone may relay the
    //     signature; the contract recovers the signer and checks it.
    // ============================================================

    function assessClaim(
        uint256 claimId,
        bool approved,
        uint256 nonce,
        uint256 deadline,
        bytes calldata signature
    ) external whenNotPaused {
        require(claimId < claimCount, "Claim does not exist");

        Claim storage claim = claims[claimId];

        require(claim.status == ClaimStatus.Submitted, "Claim already assessed");
        require(block.timestamp <= deadline, "Signature expired");
        require(!usedAssessmentNonce[nonce], "Assessment nonce already used");

        bytes32 digest = getAssessmentDigest(claimId, approved, nonce, deadline);
        address recoveredSigner = _recoverSigner(digest, signature);

        require(recoveredSigner == assessor, "Invalid assessor signature");

        // Effects
        usedAssessmentNonce[nonce] = true;
        claim.nonce = nonce;
        claim.status = approved ? ClaimStatus.Approved : ClaimStatus.Rejected;

        emit ClaimAssessed(claimId, approved, nonce);
    }

    // ============================================================
    // 14. PAY AN APPROVED CLAIM
    //     The claimant can pull the payout, so the insurer cannot
    //     delay an approved claim. Checks-Effects-Interactions.
    // ============================================================

    function payClaim(uint256 claimId) external whenNotPaused nonReentrant {
        require(claimId < claimCount, "Claim does not exist");

        Claim storage claim = claims[claimId];

        require(
            msg.sender == claim.claimant || msg.sender == insurer,
            "Not authorised"
        );
        require(claim.status == ClaimStatus.Approved, "Claim not approved");
        require(address(this).balance >= claim.amount, "Insufficient contract balance");

        // Checks done -> Effects
        uint256 paymentAmount = claim.amount;
        address claimant = claim.claimant;
        claim.status = ClaimStatus.Paid;

        // Interaction
        (bool success, ) = payable(claimant).call{value: paymentAmount}("");
        require(success, "Payment failed");

        emit ClaimPaid(claimId, claimant, paymentAmount);
    }

    // ============================================================
    // 15. CIRCUIT BREAKER
    // ============================================================

    function pause() external onlyInsurer {
        paused = true;
        emit ContractPaused(msg.sender);
    }

    function unpause() external onlyInsurer {
        paused = false;
        emit ContractUnpaused(msg.sender);
    }

    // ============================================================
    // 16. VIEW FUNCTIONS
    // ============================================================

    function getAssessmentDigest(
        uint256 claimId,
        bool approved,
        uint256 nonce,
        uint256 deadline
    ) public view returns (bytes32) {
        bytes32 structHash = keccak256(
            abi.encode(ASSESSMENT_TYPEHASH, claimId, approved, nonce, deadline)
        );
        return keccak256(abi.encodePacked("\x19\x01", DOMAIN_SEPARATOR, structHash));
    }

    function getClaim(uint256 claimId)
        external
        view
        returns (
            address claimant,
            uint256 amount,
            bytes32 evidenceHash,
            ClaimStatus status,
            uint256 nonce,
            uint256 submittedAt
        )
    {
        require(claimId < claimCount, "Claim does not exist");
        Claim memory c = claims[claimId];
        return (c.claimant, c.amount, c.evidenceHash, c.status, c.nonce, c.submittedAt);
    }

    function getContractBalance() external view returns (uint256) {
        return address(this).balance;
    }

    // ============================================================
    // 17. ECDSA SIGNATURE RECOVERY (secp256k1)
    // ============================================================

    function _recoverSigner(bytes32 digest, bytes calldata signature)
        internal
        pure
        returns (address)
    {
        require(signature.length == 65, "Invalid signature length");

        bytes32 r;
        bytes32 s;
        uint8 v;

        assembly {
            r := calldataload(signature.offset)
            s := calldataload(add(signature.offset, 32))
            v := byte(0, calldataload(add(signature.offset, 64)))
        }

        require(v == 27 || v == 28, "Invalid signature v");

        // EIP-2: reject high-s signatures to prevent malleability
        require(
            uint256(s) <= 0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0,
            "Invalid signature s"
        );

        address signer = ecrecover(digest, v, r, s);
        require(signer != address(0), "Invalid signer");

        return signer;
    }
}