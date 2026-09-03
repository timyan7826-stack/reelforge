"""Command-line interface for ReelForge."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from reelforge import __version__
from reelforge.config import load_config, write_example_config
from reelforge.pipeline import run_pipeline


def _cmd_init(args: argparse.Namespace) -> int:
    path = write_example_config(args.config)
    print(f"Wrote example config to {path}")
    print("Next: edit it, then run:")
    print(f'  reelforge run -c {path} --topic "你的主题"')
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    topic = args.topic or cfg["topic"].get("default", "")
    result = run_pipeline(cfg, topic, out_root=args.out, run_id=args.run_id)
    video = result["final_video"]
    if video:
        print(f"\n  ▶ final video: {video}")
    return 0


def _cmd_version(_: argparse.Namespace) -> int:
    print(f"reelforge {__version__}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reelforge",
        description="Deterministic, modular, batch-first AI short-video generation engine.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="write an example config.toml")
    p_init.add_argument("-c", "--config", default="config.toml")
    p_init.set_defaults(func=_cmd_init)

    p_run = sub.add_parser("run", help="run the pipeline for a topic")
    p_run.add_argument("-c", "--config", default="config.toml")
    p_run.add_argument("-t", "--topic", default="", help="video topic (overrides config)")
    p_run.add_argument("-o", "--out", default=None, help="output root directory")
    p_run.add_argument("--run-id", default=None, help="explicit run id (deterministic path)")
    p_run.set_defaults(func=_cmd_run)

    p_ver = sub.add_parser("version", help="print version")
    p_ver.set_defaults(func=_cmd_version)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
