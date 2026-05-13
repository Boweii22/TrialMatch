#!/usr/bin/env python3
"""
generate_training_data.py  —  Step 1 of the fine-tuning pipeline.

Run this once (ideally overnight) to build the training dataset.
It uses Gemma 4 to write synthetic patient profiles for real trials,
then runs each profile through the existing TrialMatch matcher to get
a ground-truth label.

Output: training_data.jsonl  (~120 labelled examples)

Usage:
    python generate_training_data.py
"""

import json
import os
import random
import time

from matcher import match_patient_to_trial
from trial_fetcher import DB_PATH
from utils import stream_response

# ── Config ────────────────────────────────────────────────────────────────────
N_TRIALS       = 60     # trials to sample from the local DB
MIN_CONFIDENCE = 65     # skip examples the model is unsure about
OUTPUT_FILE    = "training_data.jsonl"
RANDOM_SEED    = 42
# ─────────────────────────────────────────────────────────────────────────────

_MATCH_PROMPT = """You are generating synthetic patient data for AI training.

TRIAL ELIGIBILITY CRITERIA:
{eligibility_criteria}

Write a realistic patient profile for a patient who CLEARLY QUALIFIES for this trial.
Make the patient clearly meet the key inclusion criteria and have none of the exclusion criteria.

Output ONLY these exact labelled fields. No other text:
PRIMARY DIAGNOSIS:
SECONDARY CONDITIONS:
CURRENT MEDICATIONS:
PATIENT AGE:
PATIENT SEX:
RECENT LAB VALUES:
RECENT PROCEDURES:
ALLERGIES:
EXCLUSION FLAGS:
CLINICAL SEVERITY:
DISEASE STABILITY:
KEY CLINICAL FACTORS:
POTENTIAL CONCERNS:"""

_NO_PROMPT = """You are generating synthetic patient data for AI training.

TRIAL ELIGIBILITY CRITERIA:
{eligibility_criteria}

Write a realistic patient profile for a patient who CLEARLY DOES NOT QUALIFY for this trial.
Make the patient fail at least one specific inclusion criterion or have an explicit exclusion.

Output ONLY these exact labelled fields. No other text:
PRIMARY DIAGNOSIS:
SECONDARY CONDITIONS:
CURRENT MEDICATIONS:
PATIENT AGE:
PATIENT SEX:
RECENT LAB VALUES:
RECENT PROCEDURES:
ALLERGIES:
EXCLUSION FLAGS:
CLINICAL SEVERITY:
DISEASE STABILITY:
KEY CLINICAL FACTORS:
POTENTIAL CONCERNS:"""

_REASONING_FIELDS = (
    "CLINICAL SEVERITY:", "DISEASE STABILITY:",
    "KEY CLINICAL FACTORS:", "POTENTIAL CONCERNS:",
)


def _generate_profile(eligibility_criteria, profile_type):
    """Ask Gemma 4 to write a synthetic patient profile."""
    template = _MATCH_PROMPT if profile_type == "match" else _NO_PROMPT
    prompt   = template.format(eligibility_criteria=eligibility_criteria[:1200])
    try:
        return stream_response(
            [{"role": "user", "content": prompt}],
            max_tokens=320,
        )
    except Exception as e:
        print(f"      ERROR generating profile: {e}")
        return None


def _split_profile(combined):
    """
    Split the combined 13-field output into raw_extraction (9 fields)
    and clinical_reasoning (4 fields) — same logic as profile_extractor.py.
    """
    extraction_lines = []
    reasoning_lines  = []
    for line in combined.split("\n"):
        if any(line.strip().upper().startswith(f) for f in _REASONING_FIELDS):
            reasoning_lines.append(line)
        elif line.strip():
            extraction_lines.append(line)
    return "\n".join(extraction_lines).strip(), "\n".join(reasoning_lines).strip()


def main():
    print("=" * 62)
    print("TrialMatch — Generating fine-tuning training data")
    print("=" * 62)
    print()

    # ── Load local database ───────────────────────────────────────────────────
    if not os.path.exists(DB_PATH):
        print("ERROR: trials_db.json not found.")
        print("Start app.py first — it will build the database automatically.")
        return

    with open(DB_PATH, encoding="utf-8") as f:
        all_trials = json.load(f)
    print(f"Loaded {len(all_trials)} trials from local database.")

    # ── Sample trials with enough eligibility text ────────────────────────────
    usable = [
        t for t in all_trials
        if len(t.get("eligibility_criteria", "")) > 300
        and t.get("nct_id", "").startswith("NCT")
    ]
    random.seed(RANDOM_SEED)
    sampled = random.sample(usable, min(N_TRIALS, len(usable)))
    print(f"Sampled {len(sampled)} trials. Generating 2 profiles per trial.")
    print(f"Estimated time: {len(sampled) * 2 * 2 // 60}–{len(sampled) * 2 * 4 // 60} minutes.\n")

    examples  = []
    skipped   = 0

    for i, trial in enumerate(sampled, 1):
        nct_id = trial["nct_id"]
        title  = trial["title"][:55]
        elig   = trial["eligibility_criteria"]
        print(f"[{i:2}/{len(sampled)}] {nct_id}  {title}…")

        for profile_type in ("match", "no"):
            label = profile_type.upper()
            print(f"         → Generating {label} profile…", end=" ", flush=True)

            raw = _generate_profile(elig, profile_type)
            if not raw or len(raw.strip()) < 50:
                print("skip (empty)")
                skipped += 1
                continue

            patient_profile, clinical_reasoning = _split_profile(raw)
            if not patient_profile:
                print("skip (parse failed)")
                skipped += 1
                continue

            # ── Run through matcher to get ground-truth label ─────────────────
            result     = match_patient_to_trial(patient_profile, clinical_reasoning, trial)
            verdict    = result.get("verdict",         "UNKNOWN")
            confidence = result.get("confidence_score", 0)
            reason     = result.get("reason",          "")
            disq       = result.get("disqualifiers",   "NONE")
            next_step  = result.get("next_step",       "")

            if verdict == "UNKNOWN" or confidence < MIN_CONFIDENCE:
                print(f"skip ({verdict} @ {confidence}%)")
                skipped += 1
                continue

            print(f"{verdict} ({confidence}%)")
            examples.append({
                "nct_id":               nct_id,
                "patient_profile":      patient_profile,
                "clinical_reasoning":   clinical_reasoning,
                "eligibility_criteria": elig[:1500],
                "verdict":              verdict,
                "confidence":           confidence,
                "reason":               reason,
                "disqualifiers":        disq,
                "next_step":            next_step,
            })

            time.sleep(0.05)

    # ── Summary ───────────────────────────────────────────────────────────────
    match_n   = sum(1 for e in examples if e["verdict"] == "MATCH")
    partial_n = sum(1 for e in examples if e["verdict"] == "PARTIAL")
    no_n      = sum(1 for e in examples if e["verdict"] == "NO")

    print()
    print(f"Generated: {len(examples)} examples  "
          f"(MATCH {match_n} / PARTIAL {partial_n} / NO {no_n})")
    print(f"Skipped:   {skipped}")

    if not examples:
        print("\nNo examples generated. Check that Ollama is running.")
        return

    # ── Save ──────────────────────────────────────────────────────────────────
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print(f"\nSaved → {OUTPUT_FILE}")
    print()
    print("Next step:")
    print("  1. Open Google Colab  (colab.research.google.com)")
    print("  2. Upload training_data.jsonl to your Google Drive")
    print("  3. Open the fine-tuning notebook (trialmatch_finetune.ipynb)")
    print("  4. Follow the instructions in the notebook")


if __name__ == "__main__":
    main()
