"""
Deterministic smoke test for the Sprockets-Cogs processing loop.

Runs against temporary SC/vault directories and stubs model calls so it never
touches the real vault and does not require Ollama.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        sc_root = root / "sc"
        vault_dir = root / "vault"

        os.environ["SPROCKETS_COGS_SC_ROOT"] = str(sc_root)
        os.environ["SPROCKETS_COGS_VAULT_DIR"] = str(vault_dir)
        os.environ["SPROCKETS_COGS_ENTITY_STATE_PATH"] = str(sc_root / "entity_state.json")

        import agentic_loop

        agentic_loop.ensure_runtime_dirs()
        input_path = agentic_loop.INPUT_DIR / "smoke.input"
        input_path.write_text(
            "---\n"
            "session_id: smoke-test\n"
            "---\n\n"
            "Call Alex about the proposal today.\n"
        )

        raw_nodes = [
            {"raw": "Call Alex about the proposal today", "type_hint": "task"},
            {"raw": "Alex", "type_hint": "contact"},
        ]
        classified = [
            {
                "node_type": "sprockets/task",
                "title": "Call Alex about the proposal",
                "date": "2026-05-02",
                "status": "active",
                "confidence": "high",
            },
            {
                "node_type": "sprockets/contact",
                "title": "Alex",
                "confidence": "high",
            },
        ]

        with patch.object(agentic_loop, "extract_nodes", return_value=raw_nodes), \
             patch.object(agentic_loop, "classify_nodes", return_value=classified):
            processed = agentic_loop.process_existing_inputs()

        expected_paths = [
            agentic_loop.ARCHIVE_DIR / "smoke.input",
            vault_dir / "Sprockets" / "tasks" / "call-alex-about-the-proposal.md",
            vault_dir / "Sprockets" / "contacts" / "alex.md",
            vault_dir / "Cogs" / "daily" / "2026-05-02 Sat.md",
            sc_root / "entity_state.json",
        ]
        missing = [path for path in expected_paths if not path.exists()]
        if processed != 1 or missing:
            print("Smoke test failed")
            print(f"processed={processed}")
            for path in missing:
                print(f"missing: {path}")
            return 1

        print("Smoke test passed")
        print(f"temp_root={root}")
        print("created:")
        for path in expected_paths:
            print(f"- {path.relative_to(root)}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
