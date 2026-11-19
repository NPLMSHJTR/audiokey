"""Markdown, JSON, and dashboard input for an audiokey run."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_reports(result: dict[str, Any], out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = out_dir / "metrics.json"
    metrics_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    manifest = {
        "schema_version": 1,
        "summary": {
            key: result[key]
            for key in (
                "queries",
                "correct",
                "accuracy",
                "tracks",
                "indexed_hashes",
                "build_s",
                "median_latency_ms",
                "median_margin",
            )
        },
        "per_condition": result["per_condition"],
        "per_query": result["per_query"],
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, separators=(",", ":")) + "\n", encoding="utf-8")

    lines = [
        "# audiokey report",
        "",
        f"- tracks: {result['tracks']}",
        f"- indexed hashes: {result['indexed_hashes']:,}",
        f"- index build: {result['build_s']} s",
        f"- queries: {result['queries']}",
        f"- rank-1 accuracy: {result['accuracy']:.1%}",
        f"- median latency: {result['median_latency_ms']} ms",
        f"- median margin (best / runner-up): {result['median_margin']}x",
        "",
        "## Accuracy by condition",
        "",
        "| condition | correct | queries | accuracy |",
        "| --- | --- | --- | --- |",
    ]
    for name, bucket in result["per_condition"].items():
        lines.append(
            f"| {name} | {bucket['correct']} | {bucket['queries']} | {bucket['accuracy']:.1%} |"
        )

    misses = [row for row in result["per_query"] if not row["correct"]]
    lines.extend(
        [
            "",
            "## Misses",
            "",
            "| query | expected | predicted | votes | margin |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    if misses:
        for row in misses:
            lines.append(
                f"| {row['query']} | {row['expected']} | {row['predicted']} | "
                f"{row['votes']} | {row['margin']}x |"
            )
    else:
        lines.append("| none | | | | |")

    report_path = out_dir / "report.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return {"report": report_path, "metrics": metrics_path, "manifest": manifest_path}
