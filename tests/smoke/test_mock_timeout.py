#!/usr/bin/env python3
"""Mock timeout contract tests for ACP state machine and completion classification."""

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SEND_SCRIPT = REPO / ".config" / "agent-workflows" / "acp" / "acp_send.py"
COMPLETION_SCRIPT = REPO / ".config" / "agent-workflows" / "acp" / "acp_completion.py"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None:
        from importlib.machinery import SourceFileLoader
        spec = importlib.util.spec_from_loader(name, SourceFileLoader(name, str(path)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MockTimeoutTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.old_home = os.environ.get("AGENT_OS_HOME")
        os.environ["AGENT_OS_HOME"] = str(self.home)

        # acp_common derives its state paths from AGENT_OS_HOME at import time.
        # Reload it for each isolated test home.
        sys.modules.pop("acp_common", None)
        self.send = load_module(
            f"acp_send_timeout_{id(self)}", SEND_SCRIPT
        )
        self.completion = load_module(
            f"acp_completion_timeout_{id(self)}", COMPLETION_SCRIPT
        )

    def tearDown(self):
        if self.old_home is None:
            os.environ.pop("AGENT_OS_HOME", None)
        else:
            os.environ["AGENT_OS_HOME"] = self.old_home
        self.temp.cleanup()

    def _create_envelope(self, objective="timeout test task"):
        args = self.send.argparse.Namespace(
            role="reviewer",
            workspace="test-ws",
            objective=objective,
            body="",
            session="",
            with_memory=True,
            json=True,
        )
        import io
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            run_id = self.send.cmd_send(args)
        finally:
            sys.stdout = old_stdout
        return run_id

    def _transition(self, run_id, new_state, reason=""):
        args = self.send.argparse.Namespace(
            run_id=run_id,
            new_state=new_state,
            reason=reason,
            source="mock_timeout_test",
            json=True,
        )
        self.send.cmd_transition(args)

    def _get_completion(self, run_id):
        args = self.completion.argparse.Namespace(
            run_id=run_id,
            json=True,
        )
        import io
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            self.completion.cmd_check(args)
        except SystemExit:
            pass
        finally:
            output = sys.stdout.getvalue()
            sys.stdout = old_stdout
        return json.loads(output)

    def test_timeout_classification_from_worker_timeout_reason(self):
        """State: running → failed with worker_timeout (600s) reason → classified as timeout."""
        run_id = self._create_envelope("timeout classification test")
        self._transition(run_id, "claimed", "Claimed for timeout test")
        self._transition(run_id, "running", "Running timeout test")
        self._transition(run_id, "failed", "worker_timeout (600s)")

        completion = self._get_completion(run_id)
        self.assertEqual(completion["state"], "failed")
        self.assertEqual(completion["classification"], "timeout")

    def test_timeout_classification_from_plain_timeout_reason(self):
        """State: running → failed with 'timeout' reason → classified as timeout."""
        run_id = self._create_envelope("plain timeout test")
        self._transition(run_id, "claimed", "Claimed")
        self._transition(run_id, "running", "Running")
        self._transition(run_id, "failed", "timeout")

        completion = self._get_completion(run_id)
        self.assertEqual(completion["state"], "failed")
        self.assertEqual(completion["classification"], "timeout")

    def test_non_timeout_failure_not_classified_as_timeout(self):
        """A failed run without timeout in reason is NOT classified as timeout."""
        run_id = self._create_envelope("generic failure test")
        self._transition(run_id, "claimed", "Claimed")
        self._transition(run_id, "running", "Running")
        self._transition(run_id, "failed", "acpx exit code 1")

        completion = self._get_completion(run_id)
        self.assertEqual(completion["state"], "failed")
        self.assertNotEqual(completion["classification"], "timeout")

    def test_valid_state_machine_path_for_timeout(self):
        """Verify the exact state transitions that occur during a timeout."""
        run_id = self._create_envelope("state machine timeout test")

        completion_initial = self._get_completion(run_id)
        self.assertEqual(completion_initial["classification"], "in_progress")

        self._transition(run_id, "claimed", "Claimed for timeout")
        c1 = self._get_completion(run_id)
        self.assertEqual(c1["classification"], "in_progress")

        self._transition(run_id, "running", "Running timeout test")
        c2 = self._get_completion(run_id)
        self.assertEqual(c2["classification"], "in_progress")

        self._transition(run_id, "failed", "worker_timeout (600s)")
        c3 = self._get_completion(run_id)
        self.assertEqual(c3["classification"], "timeout")
        self.assertEqual(c3["state"], "failed")

    def test_history_records_timeout_reason(self):
        """The envelope history must contain the timeout reason entry."""
        run_id = self._create_envelope("history timeout test")
        self._transition(run_id, "claimed", "Claimed")
        self._transition(run_id, "running", "Running")
        self._transition(run_id, "failed", "worker_timeout (600s)")

        envelope_path = self.home / ".local" / "state" / "agent-os" / "acp" / "runs" / run_id / "envelope.json"
        with open(envelope_path) as f:
            envelope = json.load(f)

        reasons = [h.get("reason", "") for h in envelope.get("history", [])]
        self.assertTrue(
            any("timeout" in r.lower() for r in reasons),
            f"Expected timeout in history reasons, got: {reasons}",
        )

    def test_terminal_state_blocks_further_transitions(self):
        """After timeout failure, no further transitions are allowed."""
        run_id = self._create_envelope("terminal state test")
        self._transition(run_id, "claimed", "Claimed")
        self._transition(run_id, "running", "Running")
        self._transition(run_id, "failed", "worker_timeout (600s)")

        with self.assertRaises(SystemExit):
            self._transition(run_id, "succeeded", "Should not work")

    def test_escalation_timeout_classified_as_timeout(self):
        """Escalation timeout (1800s) reason is classified as timeout."""
        run_id = self._create_envelope("escalation timeout test")
        self._transition(run_id, "claimed", "Escalated")
        self._transition(run_id, "running", "Running escalation")
        self._transition(run_id, "failed", "worker_timeout (1800s)")

        completion = self._get_completion(run_id)
        self.assertEqual(completion["state"], "failed")
        self.assertEqual(completion["classification"], "timeout")

    def test_cancelled_not_classified_as_timeout(self):
        """A cancelled run is classified as cancelled, not timeout."""
        run_id = self._create_envelope("cancel vs timeout test")
        self._transition(run_id, "claimed", "Claimed")
        self._transition(run_id, "running", "Running")
        self._transition(run_id, "cancelled", "User cancelled")

        completion = self._get_completion(run_id)
        self.assertEqual(completion["state"], "cancelled")
        self.assertEqual(completion["classification"], "cancelled")

    def test_succeeded_not_classified_as_timeout(self):
        """A succeeded run is classified as success, not timeout."""
        run_id = self._create_envelope("success vs timeout test")
        self._transition(run_id, "claimed", "Claimed")
        self._transition(run_id, "running", "Running")
        self._transition(run_id, "succeeded", "Done")

        completion = self._get_completion(run_id)
        self.assertEqual(completion["state"], "succeeded")
        self.assertEqual(completion["classification"], "success")

    def test_review_to_timeout_path(self):
        """Transition through review → running → failed(timeout) classifies correctly."""
        run_id = self._create_envelope("review to timeout test")
        self._transition(run_id, "claimed", "Claimed")
        self._transition(run_id, "running", "Running")
        self._transition(run_id, "review", "Reviewing")
        self._transition(run_id, "running", "Resumed for retry")
        self._transition(run_id, "failed", "worker_timeout (600s)")

        completion = self._get_completion(run_id)
        self.assertEqual(completion["state"], "failed")
        self.assertEqual(completion["classification"], "timeout")

    def test_all_active_states_classify_as_in_progress(self):
        """Queued, claimed, and running states all classify as in_progress."""
        states_to_test = ["queued", "claimed", "running"]
        for target_state in states_to_test:
            run_id = self._create_envelope(f"in_progress {target_state} test")
            if target_state in {"claimed", "running", "review", "resume"}:
                self._transition(run_id, "claimed", "Claimed")
            if target_state in {"running", "review", "resume"}:
                self._transition(run_id, "running", "Running")
            if target_state == "review":
                self._transition(run_id, "review", "In review")

            completion = self._get_completion(run_id)
            self.assertEqual(
                completion["classification"], "in_progress",
                f"State '{target_state}' should classify as in_progress, got '{completion['classification']}'",
            )

    def test_invalid_transition_rejected(self):
        """Skipping states (e.g. queued → running) is rejected."""
        run_id = self._create_envelope("invalid transition test")
        with self.assertRaises(SystemExit):
            self._transition(run_id, "running", "Skip claimed")


if __name__ == "__main__":
    unittest.main()
