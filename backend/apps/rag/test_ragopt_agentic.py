"""Unit tests for RAG optimization spec Phase 5/6/7 (agentic + feedback)."""

from unittest.mock import Mock

from django.test import SimpleTestCase

from apps.rag.iterative import retrieve_with_refinement
from apps.rag.self_critique import critique_and_revise


def _row(chunk_id, doc_id, score):
    return {"id": chunk_id, "document_id": doc_id, "rerank_score": score, "score": score}


class RetrieveWithRefinementTest(SimpleTestCase):
    def test_high_confidence_stops_after_one_round(self):
        retriever = Mock()
        retriever.search.return_value = [
            _row("a", "d1", 0.9),
            _row("b", "d2", 0.85),
        ]
        llm = Mock()
        chunks, rounds, refined = retrieve_with_refinement(
            retriever, "q", llm=llm, max_rounds=2, search_kwargs={"top_k": 5}
        )
        self.assertEqual(rounds, 1)
        self.assertFalse(refined)
        llm.complete.assert_not_called()

    def test_low_confidence_triggers_second_round_and_merges(self):
        retriever = Mock()
        retriever.search.side_effect = [
            [_row("a", "d1", 0.3)],  # weak first round
            [_row("a", "d1", 0.3), _row("b", "d2", 0.8)],  # refined adds b
        ]
        llm = Mock()
        llm.complete.return_value = "更宽泛的查询"
        chunks, rounds, refined = retrieve_with_refinement(
            retriever, "q", llm=llm, max_rounds=2, search_kwargs={"top_k": 5}
        )
        self.assertEqual(rounds, 2)
        self.assertTrue(refined)
        self.assertIn("b", [c["id"] for c in chunks])

    def test_no_new_chunks_stops(self):
        retriever = Mock()
        retriever.search.side_effect = [
            [_row("a", "d1", 0.3)],
            [_row("a", "d1", 0.3)],  # nothing new
        ]
        llm = Mock()
        llm.complete.return_value = "rewrite"
        _chunks, rounds, refined = retrieve_with_refinement(
            retriever, "q", llm=llm, max_rounds=2, search_kwargs={"top_k": 5}
        )
        self.assertEqual(rounds, 2)
        self.assertFalse(refined)

    def test_fast_mode_single_round_never_rewrites(self):
        retriever = Mock()
        retriever.search.return_value = [_row("a", "d1", 0.3)]
        llm = Mock()
        _chunks, rounds, refined = retrieve_with_refinement(
            retriever, "q", llm=llm, max_rounds=1, search_kwargs={"top_k": 5}
        )
        self.assertEqual(rounds, 1)
        llm.complete.assert_not_called()


class CritiqueAndReviseTest(SimpleTestCase):
    def test_clean_critique_keeps_draft(self):
        llm = Mock()
        llm.complete.return_value = "OK"
        out = critique_and_revise(llm, question="q", context="ctx", draft="draft")
        self.assertEqual(out, "draft")
        self.assertEqual(llm.complete.call_count, 1)  # no revise call

    def test_issues_trigger_revision(self):
        llm = Mock()
        llm.complete.side_effect = ["第2句无依据", "修订后的答案"]
        out = critique_and_revise(llm, question="q", context="ctx", draft="draft")
        self.assertEqual(out, "修订后的答案")

    def test_critic_failure_degrades_to_draft(self):
        llm = Mock()
        llm.complete.side_effect = RuntimeError("provider down")
        out = critique_and_revise(llm, question="q", context="ctx", draft="draft")
        self.assertEqual(out, "draft")

    def test_empty_draft_short_circuits(self):
        llm = Mock()
        out = critique_and_revise(llm, question="q", context="ctx", draft="")
        self.assertEqual(out, "")
        llm.complete.assert_not_called()
