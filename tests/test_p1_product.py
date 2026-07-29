from __future__ import annotations

import tempfile
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


if __name__ == "__main__":
    unittest.main()
