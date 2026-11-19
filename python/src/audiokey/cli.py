"""Command-line interface for audiokey."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .evaluate import evaluate
from .gen import generate
from .report import write_reports

EXIT_OK = 0
EXIT_ERROR = 2
ROOT = Path(__file__).resolve().parents[3]
DASHBOARD = ROOT / "web" / "dashboard.ts"


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} does not contain a JSON object")
    return payload


def cmd_gen(args: argparse.Namespace) -> int:
    truth = generate(
        Path(args.tracks_dir),
        Path(args.queries_dir),
        Path(args.truth),
        tracks=args.tracks,
        seed=args.seed,
        clip=args.clip,
    )
    written = truth.get("queries")
    query_count = len(written) if isinstance(written, list) else 0
    print(
        f"wrote {truth.get('tracks')} tracks to {args.tracks_dir} and "
        f"{query_count} queries to {args.queries_dir}"
    )
    return EXIT_OK


def cmd_run(args: argparse.Namespace) -> int:
    workdir = Path(args.workdir)
    tracks_dir = workdir / "tracks"
    queries_dir = workdir / "queries"
    truth_path = workdir / "truth.json"
    results_path = workdir / "results.json"

    truth = generate(
        tracks_dir, queries_dir, truth_path, tracks=args.tracks, seed=args.seed, clip=args.clip
    )
    sources = sorted(str(path) for path in (ROOT / "java" / "src" / "audiokey").glob("*.java"))
    classes = workdir / "classes"
    subprocess.run(["javac", "-d", str(classes), *sources], check=True)
    subprocess.run(
        [
            "java",
            "-cp",
            str(classes),
            "audiokey.Match",
            "--tracks",
            str(tracks_dir),
            "--queries",
            str(queries_dir),
            "--out",
            str(results_path),
        ],
        check=True,
    )

    result = evaluate(truth, _load(results_path))
    paths = write_reports(result, workdir / "reports")

    print(f"audiokey {__version__}  {result['tracks']} tracks  {result['queries']} queries")
    print(
        f"accuracy {result['accuracy']:.1%} ({result['correct']}/{result['queries']})  "
        f"median latency {result['median_latency_ms']} ms  margin {result['median_margin']}x"
    )
    for name, bucket in result["per_condition"].items():
        print(f"  {name:<8} {bucket['correct']}/{bucket['queries']}  {bucket['accuracy']:.0%}")
    print(f"report: {paths['report']}")

    if args.ui:
        node = shutil.which("node")
        if node is None:
            raise ValueError("node is required to build the dashboard")
        subprocess.run(
            [
                node,
                "--experimental-strip-types",
                str(DASHBOARD),
                "--manifest",
                str(paths["manifest"]),
                "--out",
                str(workdir / "reports" / "dashboard.html"),
            ],
            check=True,
        )
        print(f"dashboard: {workdir / 'reports' / 'dashboard.html'}")
    return EXIT_OK


def cmd_eval(args: argparse.Namespace) -> int:
    truth = _load(Path(args.truth))
    result = evaluate(truth, _load(Path(args.results)))
    paths = write_reports(result, Path(args.out))
    print(f"accuracy {result['accuracy']:.1%} ({result['correct']}/{result['queries']})")
    print(f"report: {paths['report']}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="audiokey",
        description="Audio fingerprint retrieval scored against known clip provenance.",
    )
    parser.add_argument("--version", action="version", version=f"audiokey {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    gen = subparsers.add_parser("gen", help="synthesise tracks and query clips")
    gen.add_argument("--tracks", type=int, default=12)
    gen.add_argument("--seed", type=int, default=23)
    gen.add_argument("--tracks-dir", default="data/tracks")
    gen.add_argument("--queries-dir", default="data/queries")
    gen.add_argument("--truth", default="data/truth.json")
    gen.add_argument("--clip", type=float, default=5.0, help="query length in seconds")
    gen.set_defaults(func=cmd_gen)

    run = subparsers.add_parser("run", help="generate, fingerprint, match, and score")
    run.add_argument("--tracks", type=int, default=12)
    run.add_argument("--seed", type=int, default=23)
    run.add_argument("--workdir", default="audiokey-run")
    run.add_argument("--clip", type=float, default=5.0, help="query length in seconds")
    run.add_argument("--ui", action="store_true", help="also build the dashboard")
    run.set_defaults(func=cmd_run)

    evaluate_cmd = subparsers.add_parser("eval", help="score an existing results file")
    evaluate_cmd.add_argument("--truth", required=True)
    evaluate_cmd.add_argument("--results", required=True)
    evaluate_cmd.add_argument("--out", default="reports")
    evaluate_cmd.set_defaults(func=cmd_eval)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"audiokey: {error}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
