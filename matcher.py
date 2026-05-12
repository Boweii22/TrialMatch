import re

from utils import TOKENS, stream_response
from prompts import MATCHING_PROMPT

_MAX_ELIGIBILITY_CHARS = 1500


def _parse_match_response(text):
    """Extract structured fields from a MATCHING_PROMPT response."""
    parsed = {
        "verdict":      "UNKNOWN",
        "confidence_score":   50,
        "reason":       text.strip(),
        "disqualifiers": "NONE",
        "next_step":    "",
    }
    for line in text.split("\n"):
        line  = line.strip()
        upper = line.upper()
        if upper.startswith("VERDICT:"):
            val = line[8:].strip().upper()
            for v in ("MATCH", "PARTIAL", "NO"):
                if v in val:
                    parsed["verdict"] = v
                    break
        elif upper.startswith("CONFIDENCE:"):
            nums = re.findall(r"\d+", line[11:])
            if nums:
                parsed["confidence_score"] = min(100, max(0, int(nums[0])))
        elif upper.startswith("REASON:"):
            parsed["reason"] = line[7:].strip()
        elif upper.startswith("DISQUALIFIERS:"):
            parsed["disqualifiers"] = line[14:].strip()
        elif upper.startswith("NEXT STEP:"):
            parsed["next_step"] = line[10:].strip()
    return parsed


def match_patient_to_trial(patient_profile, clinical_reasoning, trial):
    """
    Match a patient to a single trial.
    trial must be a clean dict as returned by trial_fetcher.fetch_trials().
    Returns a rich dict with all fields needed by app.py and extras.py.
    """
    # ── Read clean fields from pre-extracted trial dict ──────────────────────
    title                = trial.get("title", "Unknown Trial")
    nct_id               = trial.get("nct_id", "Unknown ID")
    eligibility_text     = trial.get("eligibility_criteria", "No eligibility criteria available.")
    eligibility_text     = eligibility_text[:_MAX_ELIGIBILITY_CHARS]
    contact_name         = trial.get("contact_name",  "Trial Coordinator")
    contact_email        = trial.get("contact_email", "see ClinicalTrials.gov")
    contact_phone        = trial.get("contact_phone", "see ClinicalTrials.gov")

    try:
        # ── Primary matching ─────────────────────────────────────────────────
        prompt = MATCHING_PROMPT.format(
            patient_profile     = patient_profile,
            clinical_reasoning  = clinical_reasoning,
            eligibility_criteria = eligibility_text,
        )
        raw    = stream_response(
            [{"role": "user", "content": prompt}],
            max_tokens=TOKENS["match"],
        )
        parsed = _parse_match_response(raw)
        disqualifier_detail = ""   # removed second LLM call — MATCHING_PROMPT disqualifiers used directly

        return {
            "trial_title":        title,
            "nct_id":             nct_id,
            "verdict":            parsed["verdict"],
            "confidence_score":         parsed["confidence_score"],
            "reason":             parsed["reason"],
            "disqualifiers":      parsed["disqualifiers"],
            "next_step":          parsed["next_step"],
            "disqualifier_detail": disqualifier_detail,
            "raw_response":         raw,
            "contact_name":       contact_name,
            "contact_email":      contact_email,
            "contact_phone":      contact_phone,
            # Pass through extra trial metadata for richer display
            "location":           trial.get("location", ""),
            "phase":              trial.get("phase", ""),
            "sponsor":            trial.get("sponsor", ""),
        }

    except Exception as e:
        return {
            "trial_title":        title,
            "nct_id":             nct_id,
            "verdict":            "ERROR",
            "confidence_score":         0,
            "reason":             f"Could not process this trial: {e}",
            "disqualifiers":      "",
            "next_step":          "",
            "disqualifier_detail": "",
            "raw_response":         f"ERROR: {e}",
            "contact_name":       contact_name,
            "contact_email":      contact_email,
            "contact_phone":      contact_phone,
            "location":           trial.get("location", ""),
            "phase":              trial.get("phase", ""),
            "sponsor":            trial.get("sponsor", ""),
        }
