"""Command-line interface for Agentic Eval Ops Kit."""

from __future__ import annotations

import argparse
import sys

from .evaluator import evaluate_scenario
from .io import load_scenario, load_scenarios_from_dir
from .report import render_batch_json, render_json, render_markdown, render_text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate voice-agent, tool-agent, video, and red-team scenarios.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    evaluate_parser = subparsers.add_parser("evaluate", help="Evaluate a single scenario JSON file.")
    evaluate_parser.add_argument("path", help="Path to scenario JSON.")
    evaluate_parser.add_argument("--format", choices=("text", "markdown", "json"), default="text")
    evaluate_parser.add_argument("--threshold", type=float, default=0.75)

    batch_parser = subparsers.add_parser("batch", help="Evaluate all JSON scenarios in a directory.")
    batch_parser.add_argument("path", help="Directory containing scenario JSON files.")
    batch_parser.add_argument("--format", choices=("text", "json"), default="text")
    batch_parser.add_argument("--threshold", type=float, default=0.75)

    args = parser.parse_args(argv)

    if args.command == "evaluate":
        evaluation = evaluate_scenario(load_scenario(args.path), threshold=args.threshold)
        print(_render_single(evaluation, args.format))
        return 0 if evaluation.decision == "pass" else 1

    evaluations = [evaluate_scenario(scenario, threshold=args.threshold) for scenario in load_scenarios_from_dir(args.path)]
    if args.format == "json":
        print(render_batch_json(evaluations))
    else:
        for evaluation in evaluations:
            print(render_text(evaluation))
            print("\n" + "=" * 72 + "\n")
    return 0 if all(evaluation.decision == "pass" for evaluation in evaluations) else 1


def _render_single(evaluation, output_format: str) -> str:
    if output_format == "json":
        return render_json(evaluation)
    if output_format == "markdown":
        return render_markdown(evaluation)
    return render_text(evaluation)


if __name__ == "__main__":
    sys.exit(main())
