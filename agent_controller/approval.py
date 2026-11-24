
# Support both direct execution and package imports
if __package__:
    from .proposal import validate_proposal
    from .receipts import sign_receipt
    from .patch_applier import (
        get_current_commit,
        ensure_clean_working_tree,
        calculate_diff_hash,
    )
else:
    from proposal import validate_proposal
    from receipts import sign_receipt
    from patch_applier import (
        get_current_commit,
        ensure_clean_working_tree,
        calculate_diff_hash,
    )


def prepare_approval(proposal: dict) -> tuple:
    """
    Validate a proposal against a clean Git baseline.

    Returns (baseline_commit, diff_hash). Raises ValueError or
    RuntimeError if the proposal cannot be approved. Shared by the
    terminal and the web window, so both apply identical checks.
    """

    if not isinstance(proposal, dict):
        raise ValueError("Invalid proposal format.")

    # Establish a clean Git baseline before displaying the proposal.
    ensure_clean_working_tree()
    baseline_commit = get_current_commit()

    # Validate the proposal, including paths and exact diff.
    validate_proposal(proposal)

    # Ensure the repository has not changed during validation.
    if get_current_commit() != baseline_commit:
        raise RuntimeError("Git baseline changed during proposal validation.")

    ensure_clean_working_tree()

    # Fingerprint the exact diff shown to the user.
    return baseline_commit, calculate_diff_hash(proposal["diff"])


def finalize_approval(baseline_commit: str, diff_hash: str) -> dict:
    """
    Create the signed receipt after the user has approved.

    Raises RuntimeError or ValueError if the repository changed while
    approval was pending.
    """

    if get_current_commit() != baseline_commit:
        raise RuntimeError("Git baseline changed while approval was pending.")

    # Reject any tracked or untracked changes made during approval.
    ensure_clean_working_tree()

    return sign_receipt(
        {
            "approved": True,
            "diff_hash": diff_hash,
            "baseline_commit": baseline_commit,
        }
    )


def request_approval(proposal: dict) -> dict | None:
    """
    Display a proposed change in the terminal and request approval.

    Returns an approval receipt, or None if rejected. This function
    does not apply any changes.
    """

    try:
        baseline_commit, diff_hash = prepare_approval(proposal)
    except (ValueError, RuntimeError) as error:
        print(f"REJECTED: Proposal validation failed: {error}")
        print("\nNo changes authorized.")
        return None

    print("\n" + "=" * 60)
    print("HUMAN APPROVAL REQUIRED")
    print("=" * 60)

    print("\nPROPOSED CHANGE:")
    print(proposal["summary"])

    print("\nFILES AFFECTED:")

    for file_path in proposal["files"]:
        print(f"  - {file_path}")

    print("\nCHANGE DETAILS:")
    print(proposal["details"])

    print("\nEXACT PROPOSED DIFF:")
    print("=" * 60)
    print(proposal["diff"])
    print("=" * 60)

    print("\n" + "-" * 60)
    print("Type APPROVE to accept this proposal.")
    print(
        "Approving will MODIFY the files listed above in your working "
        "tree. The change is not committed."
    )
    print("Anything else will reject it.")

    decision = input("\nYour decision: ").strip()

    if decision != "APPROVE":
        print("\nProposal rejected. No changes authorized.")
        return None

    try:
        receipt = finalize_approval(baseline_commit, diff_hash)
    except (ValueError, RuntimeError) as error:
        print(f"\nREJECTED: Approval verification failed: {error}")
        print("A new proposal and approval are required.")
        return None

    print("\nProposal approved by the user.")
    print("Approval receipt created.")

    return receipt
