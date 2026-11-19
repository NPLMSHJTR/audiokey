"""Accuracy, margin, and latency, broken down by query condition."""

from __future__ import annotations

from typing import Any


def evaluate(truth: dict[str, Any], results: dict[str, Any]) -> dict[str, Any]:
    """Score rank-1 retrieval against the generator's provenance."""
    expected = {entry["query"]: entry for entry in truth.get("queries", [])}
    per_query: list[dict[str, Any]] = []
    per_condition: dict[str, dict[str, Any]] = {}
    correct = 0
    margins: list[float] = []
    latencies: list[float] = []

    for row in results.get("queries", []):
        name = row.get("query")
        entry = expected.get(name)
        if entry is None:
            continue
        hit = row.get("track") == entry["track"]
        correct += 1 if hit else 0
        margins.append(float(row.get("margin") or 0.0))
        latencies.append(float(row.get("latency_ms") or 0.0))
        condition = str(entry["condition"])
        bucket = per_condition.setdefault(condition, {"queries": 0, "correct": 0})
        bucket["queries"] += 1
        bucket["correct"] += 1 if hit else 0
        per_query.append(
            {
                "query": name,
                "expected": entry["track"],
                "predicted": row.get("track"),
                "condition": condition,
                "votes": row.get("votes"),
                "margin": row.get("margin"),
                "correct": hit,
            }
        )

    total = len(per_query)
    for bucket in per_condition.values():
        bucket["accuracy"] = (
            round(bucket["correct"] / bucket["queries"], 4) if bucket["queries"] else 0.0
        )

    return {
        "queries": total,
        "correct": correct,
        "accuracy": round(correct / total, 4) if total else 0.0,
        "tracks": results.get("tracks"),
        "indexed_hashes": results.get("indexed_hashes"),
        "build_s": results.get("build_s"),
        "median_latency_ms": round(sorted(latencies)[len(latencies) // 2], 2)
        if latencies
        else None,
        "median_margin": round(sorted(margins)[len(margins) // 2], 2) if margins else None,
        "per_condition": dict(sorted(per_condition.items())),
        "per_query": per_query,
    }
