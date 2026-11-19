"""Synthesise tracks and query clips with known provenance.

Each track is a four-chord loop with a pentatonic melody on top, rendered at
8 kHz. Queries are 5-second excerpts with one of four transformations applied, so
accuracy can be reported per condition rather than as a single average that hides
where the fingerprint breaks.
"""

from __future__ import annotations

import json
import math
import random
import wave
from array import array
from pathlib import Path

SAMPLE_RATE = 8000
DURATION = 20.0
CLIP = 5.0
CONDITIONS = ("clean", "gain", "noise15", "noise5")
DEFAULT_CLIP = 5.0


def _midi(note: int) -> float:
    return 440.0 * 2 ** ((note - 69) / 12.0)


def _render_note(
    buffer: array[int], start: int, length: int, frequency: float, amplitude: float
) -> None:
    """Add one decaying note with two harmonics into the buffer."""
    end = min(len(buffer), start + length)
    attack = int(SAMPLE_RATE * 0.01)
    for index in range(start, end):
        offset = index - start
        envelope = min(1.0, offset / max(1, attack)) * math.exp(-3.0 * offset / max(1, length))
        phase = 2 * math.pi * frequency * offset / SAMPLE_RATE
        value = (
            (math.sin(phase) + 0.4 * math.sin(2 * phase) + 0.15 * math.sin(3 * phase))
            * amplitude
            * envelope
        )
        buffer[index] = max(-32768, min(32767, buffer[index] + int(value * 32767)))


def _track(seed: int) -> array[int]:
    rng = random.Random(seed)
    root = 48 + rng.randrange(0, 7)
    progression = [(0, 4, 7), (7, 11, 14), (9, 12, 16), (5, 9, 12)]
    samples = array("h", [0] * int(SAMPLE_RATE * DURATION))

    chord_length = DURATION / len(progression)
    for chord_index, chord in enumerate(progression):
        start = int(chord_index * chord_length * SAMPLE_RATE)
        length = int(chord_length * SAMPLE_RATE)
        for interval in chord:
            _render_note(samples, start, length, _midi(root + interval), 0.22)

    scale = [0, 2, 4, 7, 9, 12, 14, 16]
    step = int(0.25 * SAMPLE_RATE)
    for index in range(int(DURATION / 0.25)):
        note = root + 12 + rng.choice(scale)
        _render_note(samples, index * step, int(step * 1.6), _midi(note), 0.30)

    for index in range(len(samples)):
        samples[index] = max(-32768, min(32767, samples[index] + rng.randint(-90, 90)))
    return samples


def _write_wav(path: Path, samples: array[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(samples.tobytes())


def _clip(
    samples: array[int], start: float, condition: str, rng: random.Random, clip: float
) -> array[int]:
    begin = int(start * SAMPLE_RATE)
    length = int(clip * SAMPLE_RATE)
    out = array("h", samples[begin : begin + length])
    if condition == "gain":
        factor = 0.45 if rng.random() < 0.5 else 2.2
        for index in range(len(out)):
            out[index] = max(-32768, min(32767, int(out[index] * factor)))
    elif condition in ("noise15", "noise5"):
        snr_db = 15.0 if condition == "noise15" else 5.0
        peak = max(1, max(abs(value) for value in out))
        noise = peak / (10 ** (snr_db / 20.0))
        for index in range(len(out)):
            out[index] = max(-32768, min(32767, int(out[index] + rng.gauss(0, noise))))
    return out


def generate(
    tracks_dir: Path,
    queries_dir: Path,
    truth_path: Path,
    tracks: int = 12,
    seed: int = 23,
    clip: float = DEFAULT_CLIP,
) -> dict[str, object]:
    """Write tracks, query clips, and a truth manifest."""
    if tracks < 3:
        raise ValueError("tracks must be at least 3")
    rng = random.Random(seed)
    tracks_dir.mkdir(parents=True, exist_ok=True)
    queries_dir.mkdir(parents=True, exist_ok=True)

    rendered: dict[str, array[int]] = {}
    for index in range(tracks):
        track_id = f"t{index + 1:02d}"
        samples = _track(seed + index)
        rendered[track_id] = samples
        _write_wav(tracks_dir / f"{track_id}.wav", samples)

    entries: list[dict[str, object]] = []
    query_index = 0
    for track_id, samples in rendered.items():
        for clip_index in range(5):
            condition = CONDITIONS[clip_index % len(CONDITIONS)]
            start = rng.uniform(0.5, DURATION - clip - 0.5)
            excerpt = _clip(samples, start, condition, rng, clip)
            name = f"q{query_index:04d}.wav"
            _write_wav(queries_dir / name, excerpt)
            entries.append(
                {
                    "query": name,
                    "track": track_id,
                    "condition": condition,
                    "start_s": round(start, 3),
                }
            )
            query_index += 1

    payload = {
        "schema_version": 1,
        "sample_rate": SAMPLE_RATE,
        "tracks": tracks,
        "clip_seconds": clip,
        "seed": seed,
        "queries": entries,
    }
    truth_path.parent.mkdir(parents=True, exist_ok=True)
    truth_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload
