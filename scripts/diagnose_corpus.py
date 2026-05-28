#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
diagnose_corpus.py — characterize the actual state of the SPA bilingual corpus.

Why this exists: v0.1 of arabic-corpus-translator was scaffolded based on
Agent B's design assumption that Y:\\Linguistics\\NewsDataForTranslation
contained ~38,886 pre-aligned EN/AR pairs in _corpus/parallel/. User
inspection (post-v0.1 ship) revealed:

  - _corpus/parallel/*.jsonl files are 0 KB (alignment not built)
  - N* article directories contain ONLY en.json OR only ar.json (never both)
  - Cross-references via translations: [{uuid, locale}] often point to
    directories that don't exist in the dataset
  - AR articles often have translations: [] (no claimed EN counterpart)

This diagnostic walks the corpus and produces an honest count of:
  - Total article directories
  - EN-only / AR-only / paired (rare) / neither
  - For EN articles with claimed translations[], how many resolve to
    existing AR dirs in the dataset
  - For AR articles with claimed translations[], how many resolve

Output: JSON report on stdout (or --output) + human-readable summary on stderr.

Python 3 stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


DEFAULT_ROOT = Path(r"Y:\Linguistics\NewsDataForTranslation")


def _is_article_dir(name: str) -> bool:
    return name.startswith("N") and name[1:].isdigit()


def scan_corpus(root: Path, sample_size: int | None = None,
                resolve_sample_size: int = 500) -> Dict[str, Any]:
    """Scan all article dirs under `root`. Optionally limit to `sample_size`.
    For up to `resolve_sample_size` EN+AR articles, also check whether their
    translations[] cross-references resolve to existing dirs.
    """
    report: Dict[str, Any] = {
        "root": str(root),
        "scanned_dirs": 0,
        "skipped_non_article_dirs": 0,
        "file_layout": Counter(),  # categories: en_only / ar_only / both / empty / other
        "translations_resolved": {"en_side": 0, "ar_side": 0},
        "translations_unresolved": {"en_side": 0, "ar_side": 0},
        "translations_empty": {"en_side": 0, "ar_side": 0},
        "translations_sample_size_each_side": resolve_sample_size,
        "sample_warnings": [],
    }
    # Build a set of existing N* dirs for fast cross-ref resolution checks.
    # This is the expensive part — but necessary to know the truth.
    sys.stderr.write("Enumerating article directories (this can take a minute on a network drive)...\n")
    sys.stderr.flush()
    all_dirs: List[str] = []
    try:
        for entry in os.scandir(root):
            if entry.is_dir() and _is_article_dir(entry.name):
                all_dirs.append(entry.name)
            else:
                report["skipped_non_article_dirs"] += 1
    except OSError as e:
        report["error"] = f"scandir failed: {e}"
        return report

    existing_uuids = set(all_dirs)
    sys.stderr.write(f"Found {len(all_dirs):,} article directories.\n")
    sys.stderr.flush()

    # Now characterize each dir's file layout. This is the second expensive pass.
    iter_dirs = all_dirs if sample_size is None else all_dirs[:sample_size]
    en_sample_for_resolution: List[str] = []
    ar_sample_for_resolution: List[str] = []

    for i, name in enumerate(iter_dirs):
        report["scanned_dirs"] += 1
        d = root / name
        try:
            files = {f.name for f in os.scandir(d) if f.is_file()}
        except OSError:
            report["file_layout"]["scandir_failed"] += 1
            continue

        has_en = "en.json" in files
        has_ar = "ar.json" in files

        if has_en and has_ar:
            category = "both"
        elif has_en:
            category = "en_only"
            if len(en_sample_for_resolution) < resolve_sample_size:
                en_sample_for_resolution.append(name)
        elif has_ar:
            category = "ar_only"
            if len(ar_sample_for_resolution) < resolve_sample_size:
                ar_sample_for_resolution.append(name)
        else:
            category = "neither"
        report["file_layout"][category] += 1

        if (i + 1) % 5000 == 0:
            sys.stderr.write(f"  ...scanned {i+1:,} dirs\n")
            sys.stderr.flush()

    report["file_layout"] = dict(report["file_layout"])

    # Check translation resolution on EN-side sample
    sys.stderr.write(f"\nChecking translation resolution on {len(en_sample_for_resolution)} EN articles...\n")
    sys.stderr.flush()
    for name in en_sample_for_resolution:
        try:
            data = json.loads((root / name / "en.json").read_text(encoding="utf-8"))
        except Exception:
            continue
        translations = data.get("translations") or []
        if not translations:
            report["translations_empty"]["en_side"] += 1
            continue
        all_resolve = all(t.get("uuid") in existing_uuids for t in translations if t.get("uuid"))
        if all_resolve and translations:
            report["translations_resolved"]["en_side"] += 1
        else:
            report["translations_unresolved"]["en_side"] += 1

    # Same for AR-side sample
    sys.stderr.write(f"Checking translation resolution on {len(ar_sample_for_resolution)} AR articles...\n")
    sys.stderr.flush()
    for name in ar_sample_for_resolution:
        try:
            data = json.loads((root / name / "ar.json").read_text(encoding="utf-8"))
        except Exception:
            continue
        translations = data.get("translations") or []
        if not translations:
            report["translations_empty"]["ar_side"] += 1
            continue
        all_resolve = all(t.get("uuid") in existing_uuids for t in translations if t.get("uuid"))
        if all_resolve and translations:
            report["translations_resolved"]["ar_side"] += 1
        else:
            report["translations_unresolved"]["ar_side"] += 1

    # Estimate alignable pair count: existing-resolved-and-paired rate × total EN dirs.
    en_only = report["file_layout"].get("en_only", 0)
    resolved_en_rate = (
        report["translations_resolved"]["en_side"]
        / max(1, len(en_sample_for_resolution))
    )
    report["estimated_alignable_en_pairs"] = int(en_only * resolved_en_rate)
    report["estimated_resolved_rate_en"] = round(resolved_en_rate, 4)

    return report


def cli_main() -> int:
    p = argparse.ArgumentParser(description="Characterize the actual state of the SPA bilingual corpus")
    p.add_argument("--root", default=str(DEFAULT_ROOT), help="Corpus root path")
    p.add_argument("--sample-size", type=int, help="Limit total dirs scanned (for fast iteration)")
    p.add_argument("--resolve-sample", type=int, default=500,
                   help="How many EN+AR articles to test cross-ref resolution on")
    p.add_argument("--output", "-o", help="Write JSON report to file")
    args = p.parse_args()

    root = Path(args.root)
    if not root.exists():
        print(f"ERROR: corpus root not found: {root}", file=sys.stderr)
        return 1

    report = scan_corpus(root, sample_size=args.sample_size,
                         resolve_sample_size=args.resolve_sample)

    out_str = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(out_str, encoding="utf-8")
    else:
        print(out_str)

    # Human-readable summary to stderr
    sys.stderr.write("\n" + "="*60 + "\n")
    sys.stderr.write("CORPUS DIAGNOSTIC SUMMARY\n")
    sys.stderr.write("="*60 + "\n")
    sys.stderr.write(f"Root: {report['root']}\n")
    sys.stderr.write(f"Scanned: {report['scanned_dirs']:,} article dirs\n")
    for layout, count in sorted(report["file_layout"].items(), key=lambda x: -x[1]):
        sys.stderr.write(f"  {layout:<20s} {count:>10,}\n")
    sys.stderr.write(f"\nEN-side resolution (sample of {report['translations_sample_size_each_side']}):\n")
    sys.stderr.write(f"  Resolved (claimed AR exists):   {report['translations_resolved']['en_side']}\n")
    sys.stderr.write(f"  Unresolved (broken cross-ref):  {report['translations_unresolved']['en_side']}\n")
    sys.stderr.write(f"  Empty translations[]:           {report['translations_empty']['en_side']}\n")
    sys.stderr.write(f"\nAR-side resolution (sample of {report['translations_sample_size_each_side']}):\n")
    sys.stderr.write(f"  Resolved:    {report['translations_resolved']['ar_side']}\n")
    sys.stderr.write(f"  Unresolved:  {report['translations_unresolved']['ar_side']}\n")
    sys.stderr.write(f"  Empty:       {report['translations_empty']['ar_side']}\n")
    sys.stderr.write(f"\nEstimated alignable EN→AR pairs: {report['estimated_alignable_en_pairs']:,}\n")
    sys.stderr.write(f"  (resolution rate on sample: {report['estimated_resolved_rate_en']*100:.1f}%)\n")
    sys.stderr.flush()

    return 0


if __name__ == "__main__":
    sys.exit(cli_main())
