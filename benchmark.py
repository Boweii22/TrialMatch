#!/usr/bin/env python3
"""
benchmark.py  —  Step 4 of the fine-tuning pipeline.

Compares the base Gemma 4 model against your fine-tuned TrialMatch model
on 20 held-out test examples from training_data.jsonl.

Prints a results table you can paste directly into your Kaggle writeup.

Usage:
    python benchmark.py
"""

import json
import os
import random
import time

import ollama

from matcher import _parse_match_response
from prompts import MATCHING_PROMPT

TRAINING_DATA = "training_data.jsonl"
N_TEST        = 20      # held-out examples to test on
RANDOM_SEED   = 99      # different seed from training so no overlap
BASE_MODEL    = "gemma4:e4b"
# After fine-tuning, pull your model from Ollama:
#   ollama pull YOUR_HF_USERNAME/trialmatch-gemma4
FINETUNED_MODEL = "trialmatch-gemma4"   # update with your actual Ollama model name


def _run_match(patient_profile, clinical_reasoning, eligibility_criteria, model_name):
    """Run one matching call and return (verdict, confidence, elapsed_seconds)."""
    prompt = MATCHING_PROMPT.format(
        patient_profile      = patient_profile[:700],
        clinical_reasoning   = clinical_reasoning[:350],
        eligibility_criteria = eligibility_criteria[:1500],
    )
    t0 = time.time()
    try:
        stream = ollama.chat(
            model    = model_name,
            messages = [{"role": "user", "content": prompt}],
            stream   = True,
            think    = False,
            options  = {"num_predict": 160},
        )
        text = ""
        for chunk in stream:
            if chunk.message.content:
                text += chunk.message.content
        elapsed = time.time() - t0
        parsed  = _parse_match_response(text.strip())
        return parsed["verdict"], parsed["confidence_score"], elapsed
    except Exception as e:
        return "ERROR", 0, time.time() - t0


def main():
    if not os.path.exists(TRAINING_DATA):
        print(f"ERROR: {TRAINING_DATA} not found. Run generate_training_data.py first.")
        return

    with open(TRAINING_DATA, encoding="utf-8") as f:
        all_examples = [json.loads(l) for l in f if l.strip()]

    if len(all_examples) < N_TEST:
        print(f"Only {len(all_examples)} examples available — using all of them.")
        n_test = len(all_examples)
    else:
        n_test = N_TEST

    random.seed(RANDOM_SEED)
    test_set = random.sample(all_examples, n_test)

    print("=" * 64)
    print("TrialMatch Benchmark — Base vs Fine-tuned Gemma 4")
    print("=" * 64)
    print(f"Test examples: {n_test}\n")

    results = []

    for i, ex in enumerate(test_set, 1):
        ground_truth = ex["verdict"]
        profile      = ex["patient_profile"]
        reasoning    = ex["clinical_reasoning"]
        elig         = ex["eligibility_criteria"]

        print(f"[{i:2}/{n_test}] Ground truth: {ground_truth}", end="  ", flush=True)

        # Base model
        base_v, base_c, base_t = _run_match(profile, reasoning, elig, BASE_MODEL)
        print(f"Base: {base_v}({base_c}%)  ", end="", flush=True)

        # Fine-tuned model
        ft_v, ft_c, ft_t = _run_match(profile, reasoning, elig, FINETUNED_MODEL)
        print(f"Fine-tuned: {ft_v}({ft_c}%)")

        results.append({
            "ground_truth":    ground_truth,
            "base_verdict":    base_v,
            "base_confidence": base_c,
            "base_time":       base_t,
            "ft_verdict":      ft_v,
            "ft_confidence":   ft_c,
            "ft_time":         ft_t,
        })

    # ── Calculate metrics ─────────────────────────────────────────────────────
    base_correct = sum(1 for r in results if r["base_verdict"] == r["ground_truth"])
    ft_correct   = sum(1 for r in results if r["ft_verdict"]   == r["ground_truth"])
    base_acc     = base_correct / len(results) * 100
    ft_acc       = ft_correct   / len(results) * 100

    base_avg_time = sum(r["base_time"] for r in results) / len(results)
    ft_avg_time   = sum(r["ft_time"]   for r in results) / len(results)

    base_avg_conf = sum(r["base_confidence"] for r in results) / len(results)
    ft_avg_conf   = sum(r["ft_confidence"]   for r in results) / len(results)

    base_match_correct = sum(
        1 for r in results
        if r["ground_truth"] == "MATCH" and r["base_verdict"] == "MATCH"
    )
    ft_match_correct = sum(
        1 for r in results
        if r["ground_truth"] == "MATCH" and r["ft_verdict"] == "MATCH"
    )
    total_matches = sum(1 for r in results if r["ground_truth"] == "MATCH")

    print()
    print("=" * 64)
    print("RESULTS")
    print("=" * 64)
    print(f"{'Metric':<35} {'Base Gemma 4':>13} {'Fine-tuned':>13}")
    print("-" * 64)
    print(f"{'Accuracy':<35} {base_acc:>12.1f}% {ft_acc:>12.1f}%")
    print(f"{'Avg confidence score':<35} {base_avg_conf:>12.1f}  {ft_avg_conf:>12.1f}")
    print(f"{'Correct MATCH verdicts':<35} {base_match_correct:>8}/{total_matches}      {ft_match_correct:>4}/{total_matches}")
    print(f"{'Avg response time (s)':<35} {base_avg_time:>12.1f}s {ft_avg_time:>12.1f}s")
    print("=" * 64)
    print()

    improvement = ft_acc - base_acc
    sign = "+" if improvement >= 0 else ""
    print(f"Accuracy improvement: {sign}{improvement:.1f} percentage points")
    print()

    # ── Save for writeup ──────────────────────────────────────────────────────
    output = {
        "n_test": n_test,
        "base_accuracy": round(base_acc, 1),
        "ft_accuracy":   round(ft_acc, 1),
        "base_avg_confidence": round(base_avg_conf, 1),
        "ft_avg_confidence":   round(ft_avg_conf, 1),
        "base_match_correct":  f"{base_match_correct}/{total_matches}",
        "ft_match_correct":    f"{ft_match_correct}/{total_matches}",
        "base_avg_time_s": round(base_avg_time, 1),
        "ft_avg_time_s":   round(ft_avg_time, 1),
        "improvement_pp":  round(improvement, 1),
    }
    with open("benchmark_results.json", "w") as f:
        json.dump(output, f, indent=2)
    print("Saved → benchmark_results.json  (paste table into Kaggle writeup)")


if __name__ == "__main__":
    main()
