#!/usr/bin/env python3
"""
Build the eval dev set from sample submissions.

Outputs eval/dev_set/cases.json with expected verdicts per line item.
Used by run_eval.py to measure system accuracy.

Usage:
    python scripts/build_dev_set.py
"""
import json
from pathlib import Path

# Ground-truth labels derived from manual policy analysis of the sample submission:
# Priya Patel (NW-05117, Grade 4, Logistics Ops, Chicago May 6-7 2025)
#
# TEP-005 §2.1: Economy default domestic. LAX→ORD is ~4h = economy class required.
#   Flight is Main Cabin (economy). ✓ compliant.
#   Amount $385.60 — within reason for domestic RT.
#
# TEP-004 §3: Chicago = Tier 2, max $250/night.
#   Hyatt $245.00 = $215 room + $30 tax. Room rate $215 ≤ $250. ✓ compliant.
#   Tax is part of the lodging bill; total $245 ≤ $250 cap. ✓ compliant.
#
# TEP-001 §4: Total $385.60 + $245.00 = $630.60 < $1,000 → Grade 4 self-approval. ✓

DEV_CASES = [
    {
        "id": "case_001",
        "description": "Priya Patel Chicago trip — flight",
        "employee": {
            "employee_id": "NW-05117",
            "grade": 4,
            "department": "Logistics Operations",
        },
        "trip": {
            "destination": "Chicago, IL",
            "purpose": "Vendor site visit",
            "start_date": "2025-05-06",
            "end_date": "2025-05-07",
        },
        "receipt": "01_american_flight.pdf",
        "expected": {
            "category": "airfare",
            "vendor": "American Airlines",
            "amount": 385.60,
            "verdict": "compliant",
            "confidence_min": 0.75,
            "must_cite": ["TEP-005"],
            "must_not_cite": [],
        },
    },
    {
        "id": "case_002",
        "description": "Priya Patel Chicago trip — hotel",
        "employee": {
            "employee_id": "NW-05117",
            "grade": 4,
            "department": "Logistics Operations",
        },
        "trip": {
            "destination": "Chicago, IL",
            "purpose": "Vendor site visit",
            "start_date": "2025-05-06",
            "end_date": "2025-05-07",
        },
        "receipt": "02_hyatt_chicago.pdf",
        "expected": {
            "category": "lodging",
            "vendor": "Hyatt Regency Chicago",
            "amount": 245.00,
            "verdict": "compliant",
            "confidence_min": 0.75,
            "must_cite": ["TEP-004"],
            "must_not_cite": [],
        },
    },
]

# Q&A test cases
QA_CASES = [
    {
        "id": "qa_001",
        "question": "What is the maximum hotel rate for Chicago?",
        "expected_status": "in_scope",
        "expected_answer_contains": ["250", "Tier 2"],
        "must_cite": ["TEP-004"],
    },
    {
        "id": "qa_002",
        "question": "Can I fly business class on a 4-hour domestic flight?",
        "expected_status": "in_scope",
        "expected_answer_contains": ["economy", "6"],
        "must_cite": ["TEP-005"],
    },
    {
        "id": "qa_003",
        "question": "Is alcohol reimbursable?",
        "expected_status": "in_scope",
        "expected_answer_contains": ["VP", "client entertainment"],
        "must_cite": ["TEP-003"],
    },
    {
        "id": "qa_004",
        "question": "What's the weather like in Chicago?",
        "expected_status": "out_of_scope",
        "expected_answer_contains": [],
        "must_cite": [],
    },
    {
        "id": "qa_005",
        "question": "What are the per-diem rates for Seattle?",
        "expected_status": "in_scope",
        "expected_answer_contains": ["per-diem", "Tier"],
        "must_cite": ["TEP-008"],
    },
]

if __name__ == "__main__":
    out_dir = Path(__file__).parent.parent / "eval" / "dev_set"
    out_dir.mkdir(parents=True, exist_ok=True)

    cases_path = out_dir / "cases.json"
    cases_path.write_text(json.dumps({"submission_cases": DEV_CASES, "qa_cases": QA_CASES}, indent=2))
    print(f"Wrote {len(DEV_CASES)} submission cases + {len(QA_CASES)} Q&A cases to {cases_path}")
