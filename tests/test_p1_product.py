from __future__ import annotations

import tempfile
import os
import time
import unittest
from pathlib import Path

import api_server
from fastapi import HTTPException

from video_rag.diagnosis import VideoJobManager
from video_rag.retrieval import VideoEvidenceRetriever


class P1ProductTests(unittest.TestCase):
    def test_required_routes_exist(self) -> None:
        routes = {(route.path, tuple(sorted(route.methods or []))) for route in api_server.app.routes}
        paths = {path for path, _methods in routes}
        self.assertTrue(
            {
                "/v2/chat",
                "/v2/video-jobs",
                "/v2/video-jobs/{job_id}",
                "/v2/video-jobs/{job_id}/result",
                "/manual-media/{image_name}",
                "/video-media/{media_path:path}",
                "/demo",
            }.issubset(paths)
        )

    def test_video_media_rejects_raw_and_traversal(self) -> None:
        for path in ("raw/private.mp4", "../.env", "processed/not-present.mp4"):
            with self.assertRaises(HTTPException):
                api_server._resolve_video_media(path)

    def test_strict_tri_hybrid_rejects_unavailable_services(self) -> None:
        retriever = VideoEvidenceRetriever(
            mode="tri_hybrid",
            dense_endpoint="http://127.0.0.1:1",
            visual_endpoint="http://127.0.0.1:1",
        )
        with self.assertRaisesRegex(RuntimeError, "requested video retrieval mode"):
            retriever.search("air fryer cooking temperature", top_k=1, strict=True)

    def test_job_paths_do_not_use_uploaded_filename(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = VideoJobManager(Path(temp_dir))
            job_id, target = manager.create(
                "../../private.mp4",
                "video/mp4",
                "question",
                "Air Fryer",
            )
            self.assertEqual(target.name, "input.mp4")
            self.assertEqual(target.parent.name, job_id)
            self.assertEqual(manager.get(job_id)["status"], "uploading")
            manager.update(job_id, status="queued")
            self.assertEqual(manager.claim_next(), job_id)
            with self.assertRaisesRegex(RuntimeError, "active video job"):
                manager.delete(job_id)
            manager.update(job_id, status="completed")
            manager.delete(job_id)
            self.assertFalse(target.parent.exists())

    def test_video_prompt_contains_temporal_citation(self) -> None:
        item = api_server.VideoEvidenceItem(
            scene_id="scene-1",
            record_id="record-1",
            product_class="Air Fryer",
            start_seconds=2.0,
            end_seconds=8.0,
            clip_url="/video-media/processed/a.mp4",
            thumbnail_url="/video-media/keyframes/a.jpg",
            score=1.0,
            evidence_text="Press the temperature button.",
            retrieval_mode="tri_hybrid",
        )
        prompt = api_server._video_evidence_prompt([item])
        self.assertIn("[VID:scene-1]", prompt)
        self.assertIn("2.0-8.0s", prompt)

    def test_non_operational_product_mentions_return_no_video(self) -> None:
        retriever = VideoEvidenceRetriever(mode="bm25")
        self.assertEqual(
            retriever.search("Tell me a joke about an air fryer", top_k=3),
            [],
        )
        self.assertEqual(
            retriever.search("air fryer warranty refund phone number", top_k=3),
            [],
        )
        self.assertEqual(
            retriever.search("Where is the fax modem on an espresso machine?", top_k=3),
            [],
        )
        self.assertEqual(
            retriever.search("压力锅怎样播放蓝光电影？", top_k=3),
            [],
        )

    def test_video_citation_requires_answer_tag(self) -> None:
        item = api_server.VideoEvidenceItem(
            scene_id="scene-1",
            record_id="record-1",
            product_class="Air Fryer",
            start_seconds=2.0,
            end_seconds=8.0,
            clip_url="/video-media/processed/a.mp4",
            thumbnail_url="/video-media/keyframes/a.jpg",
            score=1.0,
            evidence_text="Press the temperature button.",
            retrieval_mode="tri_hybrid",
        )
        citations, _images = api_server._structured_evidence(
            "Press the button.",
            [],
            [item],
            {"events": []},
        )
        self.assertEqual(citations, [])
        citations, _images = api_server._structured_evidence(
            "Press the button. [VID:scene-1]",
            [],
            [item],
            {"events": []},
        )
        self.assertEqual([citation.source_id for citation in citations], ["scene-1"])

    def test_manual_image_id_resolves_to_existing_authenticated_asset(self) -> None:
        filename = api_server._manual_image_filename("Manual08_0")
        self.assertEqual(filename, "Manual08_0.jpg")
        root = Path(api_server.__file__).resolve().parent / "手册" / "插图"
        self.assertTrue((root / filename).is_file())

    def test_chinese_manual_evidence_supports_answer_sentence(self) -> None:
        trace = {
            "events": [
                {
                    "kind": "pre_retrieval",
                    "sections": [
                        {
                            "chunk_id": 8,
                            "product": "Air Fryer",
                            "heading": "控制面板",
                            "section_summary": "使用温度按钮调节烹饪温度。",
                            "pics": [],
                        }
                    ],
                }
            ]
        }
        citations, _images = api_server._structured_evidence(
            "按下温度按钮设置温度。",
            [],
            [],
            trace,
        )
        self.assertEqual(len(citations), 1)
        self.assertEqual(citations[0].supports, ["sentence-1"])

    def test_failed_upload_can_be_discarded_and_stale_lock_recovers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = VideoJobManager(Path(temp_dir))
            job_id, target = manager.create(
                "clip.mp4",
                "video/mp4",
                "",
                "Air Fryer",
            )
            target.write_bytes(b"partial")
            manager.discard_upload(job_id)
            self.assertFalse(target.parent.exists())

            job_id, _target = manager.create(
                "clip.mp4",
                "video/mp4",
                "",
                "Air Fryer",
            )
            lock_path = Path(temp_dir) / job_id / ".state.lock"
            lock_path.write_text("", encoding="utf-8")
            old = time.time() - 600
            os.utime(lock_path, (old, old))
            manager.update(job_id, status="queued")
            self.assertEqual(manager.get(job_id)["status"], "queued")


if __name__ == "__main__":
    unittest.main()
