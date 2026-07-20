"""Phase 7C operational runbook and regression-closure guardrails."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[3]
_REPO_ROOT_AVAILABLE = (ROOT / "SPEC.MD").exists()


@unittest.skipUnless(
    _REPO_ROOT_AVAILABLE,
    "repo-root artifacts not available in this layout; run on host",
)
class OperationalRunbookTest(SimpleTestCase):
    def test_v9_runbook_covers_required_operator_flows(self):
        runbook = ROOT / "docs" / "operations" / "KnowPilot_V9_Operations_Runbook.md"
        self.assertTrue(runbook.exists())
        text = runbook.read_text(encoding="utf-8")
        for required in [
            "health degraded",
            "export job failed",
            "SLA backlog",
            "migration",
            "deploy check",
            "smoke script",
            "rollback",
        ]:
            self.assertIn(required, text)


@unittest.skipUnless(
    _REPO_ROOT_AVAILABLE,
    "repo-root artifacts not available in this layout; run on host",
)
class V9SmokeScriptTest(SimpleTestCase):
    def test_v9_smoke_script_validates_frontend_build_artifacts(self):
        script = ROOT / "backend" / "scripts" / "smoke_v9_operations.py"
        self.assertTrue(script.exists())
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            (dist / "assets").mkdir()
            (dist / "index.html").write_text("<div id='root'></div>", encoding="utf-8")
            (dist / "assets" / "index.js").write_text("console.log('ok')", encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--check-build-only",
                    "--frontend-dist",
                    str(dist),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "pass")
        self.assertIn("frontend_build_artifacts", str(payload))

    def test_v9_smoke_api_mode_fails_safely_without_traceback(self):
        script = ROOT / "backend" / "scripts" / "smoke_v9_operations.py"
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            (dist / "assets").mkdir()
            (dist / "index.html").write_text("<div id='root'></div>", encoding="utf-8")
            (dist / "assets" / "index.js").write_text("console.log('ok')", encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--frontend-dist",
                    str(dist),
                    "--base-url",
                    "http://127.0.0.1:9/api/v1/",
                    "--token",
                    "not-a-real-token",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr + result.stdout)
        payload = json.loads(result.stderr)
        self.assertEqual(payload["status"], "fail")
        self.assertIn("error", payload)


@unittest.skipUnless(
    _REPO_ROOT_AVAILABLE,
    "repo-root artifacts not available in this layout; run on host",
)
class Phase7DocumentationClosureTest(SimpleTestCase):
    def test_phase7_docs_close_v9_line_and_point_to_next_candidate(self):
        spec = (ROOT / "SPEC.MD").read_text(encoding="utf-8")
        progress = (ROOT / "progress.md").read_text(encoding="utf-8")
        roadmap = (ROOT / "docs" / "superpowers" / "plans" / "KnowPilot-long-term-roadmap.md").read_text(encoding="utf-8")

        self.assertIn("Phase 7C", spec)
        self.assertIn("V9.2", spec)
        self.assertIn("Phase 7C V9.2", progress)
        self.assertIn("Phase 7 = V9.0", progress)
        self.assertIn("V9.0 / Phase 7A", roadmap)
        self.assertIn("V9.1 / Phase 7B", roadmap)
        self.assertIn("V9.2 / Phase 7C", roadmap)
        self.assertIn("V10.0", roadmap)
