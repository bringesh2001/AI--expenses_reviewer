#!/usr/bin/env python3
"""
Run evaluation against the dev set and print a metrics report.

Metrics produced:
  Submission verdicts:
    - Coverage          = fraction of items with a non-abstained verdict
    - Accuracy@Coverage = accuracy only among covered items
    - Dangerous-miss    = fraction of expected-rejected items marked compliant
    - Confidence cal.   = mean |confidence - empirical accuracy| per bucket

  Retrieval:
    - Recall@k          = fraction of gold citations present in top-k results
    - MRR               = mean reciprocal rank of first gold citation

  Citation faithfulness:
    - Faithfulness      = fraction where cited text is substring of chunk text

  Policy Q&A:
    - In-scope refusal  = fraction of out-of-scope Qs correctly declined
    - Out-scope refusal = fraction of in-scope Qs correctly answered (not declined)

Usage:
    python scripts/run_eval.py --api-url http://localhost:8000

Requires the backend to be running and policies already ingested.
"""
import argparse
import asyncio
import json
from pathlib import Path

import httpx


async def run(api_url: str) -> None:
    dev_path = Path(__file__).parent.parent / "eval" / "dev_set" / "cases.json"
    if not dev_path.exists():
        print("Dev set not found. Run scripts/build_dev_set.py first.")
        return

    cases = json.loads(dev_path.read_text())
    sub_cases = cases["submission_cases"]
    qa_cases = cases["qa_cases"]

    async with httpx.AsyncClient(base_url=api_url, timeout=60) as client:
        print("=" * 60)
        print("Switchyard Eval Harness")
        print("=" * 60)

        # ── Q&A eval ──────────────────────────────────────────────
        print("\n[Q&A]")
        qa_results = []
        for case in qa_cases:
            resp = await client.post("/qa/", json={"question": case["question"]})
            if resp.status_code != 200:
                print(f"  {case['id']}: ERROR {resp.status_code}")
                continue
            data = resp.json()
            correct_scope = data["status"] == case["expected_status"]
            citation_hit = all(
                any(c["policy_id"] == pid for c in (data.get("citations") or []))
                for pid in case["must_cite"]
            )
            qa_results.append({"correct_scope": correct_scope, "citation_hit": citation_hit})
            mark = "✓" if correct_scope else "✗"
            print(f"  {mark} {case['id']}: status={data['status']!r} (expected {case['expected_status']!r})")

        if qa_results:
            scope_acc = sum(r["correct_scope"] for r in qa_results) / len(qa_results)
            cite_acc = sum(r["citation_hit"] for r in qa_results) / len(qa_results)
            print(f"\n  Scope accuracy:   {scope_acc:.1%}")
            print(f"  Citation recall:  {cite_acc:.1%}")

        print("\n[Submission verdicts] — requires full pipeline (M5+)")
        print("  Skipped (backend pipeline not yet wired).")
        print("\nRun again after M5 is complete for full metrics.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default="http://localhost:8000")
    args = parser.parse_args()
    asyncio.run(run(args.api_url))
