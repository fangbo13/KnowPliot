"""Phase 6C release-readiness guardrails."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from django.test import SimpleTestCase

from apps.chat.models import ComplianceExportJob, Feedback, KnowledgeGapTicket


ROOT = Path(__file__).resolve().parents[3]
_REPO_ROOT_AVAILABLE = (ROOT / "SPEC.MD").exists()


class ReleaseReadinessIndexTest(SimpleTestCase):
    def _index_fields(self, model):
        return {tuple(index.fields) for index in model._meta.indexes}

    def test_quality_models_have_release_query_indexes(self):
        self.assertIn(("space", "status", "created_at"), self._index_fields(Feedback))
        self.assertIn(("space", "status", "created_at"), self._index_fields(KnowledgeGapTicket))
        self.assertIn(
            ("status", "requested_by", "created_at"),
            self._index_fields(ComplianceExportJob),
        )


@unittest.skipUnless(
    _REPO_ROOT_AVAILABLE,
    "repo-root artifacts not available in this layout; run on host",
)
class ReleaseSmokeScriptTest(SimpleTestCase):
    def test_smoke_script_can_validate_frontend_build_artifacts(self):
        script = ROOT / "backend" / "scripts" / "smoke_v8_release.py"
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
        self.assertIn("frontend_build_artifacts", result.stdout)


@unittest.skipUnless(
    _REPO_ROOT_AVAILABLE,
    "repo-root artifacts not available in this layout; run on host",
)
class ReleaseDocumentationTest(SimpleTestCase):
    def test_release_docs_track_v8_2_and_next_v9_stage(self):
        spec = (ROOT / "SPEC.MD").read_text(encoding="utf-8")
        progress = (ROOT / "progress.md").read_text(encoding="utf-8")
        roadmap = (ROOT / "docs" / "superpowers" / "plans" / "KnowPilot-long-term-roadmap.md").read_text(encoding="utf-8")

        self.assertIn("Phase 6C", spec)
        self.assertIn("V8.2", spec)
        self.assertIn("Long-Run Operations / Scale Hardening", spec)
        self.assertIn("Phase 6C V8.2", progress)
        self.assertIn("V8.0", roadmap)
        self.assertIn("V8.1", roadmap)
        self.assertIn("V8.2", roadmap)
