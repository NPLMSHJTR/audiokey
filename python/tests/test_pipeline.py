"""Tests for audio synthesis and retrieval scoring."""

from __future__ import annotations

import json
import tempfile
import unittest
import wave
from pathlib import Path

from audiokey.evaluate import evaluate
from audiokey.gen import generate


class GeneratorTests(unittest.TestCase):
    def test_writes_tracks_queries_and_truth(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            truth = generate(
                root / "tracks", root / "queries", root / "truth.json", tracks=3, seed=5
            )
            tracks = sorted((root / "tracks").glob("*.wav"))
            queries = sorted((root / "queries").glob("*.wav"))
            self.assertEqual(len(tracks), 3)
            self.assertEqual(len(queries), 15)
            self.assertEqual(len(truth["queries"]), 15)

            with wave.open(str(tracks[0]), "rb") as handle:
                self.assertEqual(handle.getnchannels(), 1)
                self.assertEqual(handle.getsampwidth(), 2)
                self.assertEqual(handle.getframerate(), 8000)

            stored = json.loads((root / "truth.json").read_text(encoding="utf-8"))
            self.assertEqual(stored["schema_version"], 1)
            self.assertEqual(stored["clip_seconds"], 5.0)

    def test_clip_length_is_configurable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            truth = generate(
                Path(tmp) / "tracks",
                Path(tmp) / "queries",
                Path(tmp) / "truth.json",
                tracks=3,
                seed=6,
                clip=3.0,
            )
            self.assertEqual(truth["clip_seconds"], 3.0)

    def test_rejects_tiny_catalogues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
            generate(Path(tmp) / "t", Path(tmp) / "q", Path(tmp) / "x.json", tracks=2)


class ScoringTests(unittest.TestCase):
    def test_accuracy_and_conditions(self) -> None:
        truth = {
            "queries": [
                {"query": "a", "track": "t01", "condition": "clean"},
                {"query": "b", "track": "t02", "condition": "noise5"},
            ]
        }
        results = {
            "tracks": 2,
            "indexed_hashes": 10,
            "build_s": 0.1,
            "queries": [
                {"query": "a", "track": "t01", "votes": 50, "margin": 4.0, "latency_ms": 5},
                {"query": "b", "track": "t01", "votes": 2, "margin": 1.0, "latency_ms": 6},
            ],
        }
        result = evaluate(truth, results)
        self.assertEqual(result["correct"], 1)
        self.assertAlmostEqual(result["accuracy"], 0.5)
        self.assertEqual(result["per_condition"]["clean"]["accuracy"], 1.0)
        self.assertEqual(result["per_condition"]["noise5"]["accuracy"], 0.0)

    def test_unknown_queries_are_ignored(self) -> None:
        truth = {"queries": [{"query": "a", "track": "t01", "condition": "clean"}]}
        results = {"queries": [{"query": "zzz", "track": "t09"}, {"query": "a", "track": "t01"}]}
        result = evaluate(truth, results)
        self.assertEqual(result["queries"], 1)
        self.assertEqual(result["accuracy"], 1.0)


if __name__ == "__main__":
    unittest.main()
