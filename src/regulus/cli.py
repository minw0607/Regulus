"""Command-line interface for Regulus.

    regulus ingest [--frameworks eu_ai_act,nist_ai_rmf] [--force]
    regulus lookup "our model was not validated for demographic bias" [--top-k 5]
    regulus frameworks
"""
from __future__ import annotations

import argparse
import sys
from typing import List

from .config import RegulusConfig
from .sources import FRAMEWORK_SOURCES
from .standards_loader import StandardsLoader


def _cmd_frameworks(_args, _config) -> int:
    for fid, src in FRAMEWORK_SOURCES.items():
        status = "fetchable" if (src.fetchable and src.url) else "manual/skip"
        print(f"  {fid:14s} [{status:11s}] {src.name}")
        if src.note:
            print(f"                 note: {src.note}")
    return 0


def _cmd_ingest(args, config) -> int:
    ids = [f.strip() for f in args.frameworks.split(",")] if args.frameworks else None
    provisions = StandardsLoader(config).load(framework_ids=ids, force_download=args.force)
    by_fw: dict[str, int] = {}
    for p in provisions:
        by_fw[p.framework_name] = by_fw.get(p.framework_name, 0) + 1
    for name, count in sorted(by_fw.items()):
        print(f"  {count:4d}  {name}")
    return 0 if provisions else 1


def _cmd_lookup(args, config) -> int:
    from .lookup import RegulusLookup

    ids = [f.strip() for f in args.frameworks.split(",")] if args.frameworks else None
    provisions = StandardsLoader(config).load(framework_ids=ids)
    if not provisions:
        print("No provisions loaded — run `regulus ingest` first or check connectivity.")
        return 1
    results = RegulusLookup(provisions, config).search(args.issue, top_k=args.top_k)
    print(f"\nTop {len(results)} applicable provisions for:\n  \"{args.issue}\"\n")
    for i, r in enumerate(results, 1):
        print(f"{i}. {r.provision.citation()}   (score {r.score:.3f})")
        print(f"   source: {r.provision.source_url}")
        print(f"   {r.snippet.strip()[:220]}...\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="regulus", description="AI governance standards lookup (RAG + knowledge graph).")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("frameworks", help="list supported frameworks").set_defaults(func=_cmd_frameworks)

    p_ingest = sub.add_parser("ingest", help="download + parse frameworks into provisions")
    p_ingest.add_argument("--frameworks", default="", help="comma-separated framework ids (default: all fetchable)")
    p_ingest.add_argument("--force", action="store_true", help="force re-download")
    p_ingest.set_defaults(func=_cmd_ingest)

    p_lookup = sub.add_parser("lookup", help="find applicable provisions for an issue")
    p_lookup.add_argument("issue", help="free-text issue or observation")
    p_lookup.add_argument("--frameworks", default="", help="comma-separated framework ids (default: all fetchable)")
    p_lookup.add_argument("--top-k", type=int, default=None, help="number of provisions to return")
    p_lookup.set_defaults(func=_cmd_lookup)

    return parser


def main(argv: List[str] | None = None) -> int:
    args = build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    return args.func(args, RegulusConfig())


if __name__ == "__main__":
    raise SystemExit(main())
