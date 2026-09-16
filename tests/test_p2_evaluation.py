from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import p2_freeze_and_evaluate as p2


class P2EvaluationTests(unittest.TestCase):
    def test_iou(self) -> None:
        self.assertEqual(p2.iou((0, 10), (20, 30)), 0.0)
        self.assertAlmostEqual(p2.iou((0, 10), (5, 15)), 1 / 3)
        self.assertEqual(p2.iou((0, 10), (0, 10)), 1.0)

    def test_fusion_uses_censored_rank(self) -> None:
        candidates = {
            "scene-a": {"ranks": {"bm25": 1}},
            "scene-b": {"ranks": {"dense": 1, "visual": 1}},
        }
        self.assertEqual(
            p2.fused_ranking(candidates, (1.0, 0.0, 0.0))[0], "scene-a"
        )
        self.assertEqual(
            p2.fused_ranking(candidates, (0.0, 0.5, 0.5))[0], "scene-b"
        )

    def test_v2_preserves_all_grades(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "data_video"
            / "releases"
            / "paper_video_retrieval_v1"
            / "manifests"
            / "paper_qrels_v1"
            / "paper_video_qrels_graded_v1.csv"
        )
        with tempfile.TemporaryDirectory() as directory:
            _, rows, no_positive = p2.freeze_qrels_v2(
                source, Path(directory)
            )
            original = p2.read_csv(source)
            self.assertEqual(len(rows), len(original))
            self.assertEqual(
                [row["relevance_grade"] for row in rows],
                [row["relevance_grade"] for row in original],
            )
            self.assertEqual(len(no_positive), 25)
            self.assertEqual(
                sum(row["primary_eval_eligible"] == "no" for row in rows), 9
            )


if __name__ == "__main__":
    unittest.main()
