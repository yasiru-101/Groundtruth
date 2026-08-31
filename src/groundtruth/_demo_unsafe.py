"""Demonstrate that destructive git operations from home are refused.

This script attempts `git add .` from the user's home directory and
shows the system refusing it with a ledger entry.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

from groundtruth.config import PROJECT_ROOT
from groundtruth.ledger.writer import LedgerWriter
from groundtruth.contracts.ledger import LedgerMode, LedgerOutcome
from groundtruth.safety.git_guard import GitGuard, GitRefusal


def main() -> None:
    home = Path.home()
    workspace_id = str(uuid.uuid4())
    run_id = f"demo-unsafe-{uuid.uuid4().hex[:8]}"

    artifacts_dir = PROJECT_ROOT / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = artifacts_dir / f"run_{run_id}" / "ledger.jsonl"
    writer = LedgerWriter(ledger_path, run_id=run_id)

    print("=" * 60)
    print("Groundtruth Safety Demo")
    print("=" * 60)
    print()
    print(f"Home directory:  {home}")
    print(f"Project root:    {PROJECT_ROOT}")
    print(f"Ledger path:     {ledger_path}")
    print()

    print("Attempting: git add . (from home directory)")
    print("-" * 40)

    guard = GitGuard(
        sandbox_path=home,
        workspace_id=workspace_id,
    )

    try:
        guard.run(["git", "add", "."])
        print("ERROR: This should have been refused!")
        sys.exit(1)
    except GitRefusal as e:
        print(f"REFUSED: {e.reason}")
        writer.append(
            actor="demo-unsafe",
            action="git_add_dot_from_home",
            mode=LedgerMode.DRY_RUN,
            subject=str(home),
            outcome=LedgerOutcome.REFUSED,
            error=e.reason,
        )
        print(f"Ledger entry written: {ledger_path}")

    print()

    banned_commands = [
        ["git", "add", "-A"],
        ["git", "add", "-u"],
        ["git", "commit", "-a", "-m", "sneaky"],
        ["git", "push", "--force"],
        ["git", "clean", "-fd"],
        ["git", "reset", "--hard"],
    ]

    for cmd in banned_commands:
        cmd_str = " ".join(cmd)
        try:
            guard.run(cmd)
            print(f"  FAIL: '{cmd_str}' was NOT refused!")
            sys.exit(1)
        except GitRefusal as e:
            writer.append(
                actor="demo-unsafe",
                action=f"banned_{cmd[1]}",
                mode=LedgerMode.DRY_RUN,
                subject=str(home),
                outcome=LedgerOutcome.REFUSED,
                error=e.reason,
            )
            print(f"  REFUSED: {cmd_str}")

    print()
    print("=" * 60)
    print("All destructive commands from home directory: REFUSED")
    print(f"Ledger at: {ledger_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
