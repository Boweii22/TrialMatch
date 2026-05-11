from utils import stream_response
from prompts import EMAIL_DRAFT_PROMPT, URDU_EXPLAIN_PROMPT

_MAX_RESULTS_FOR_URDU = 2500   # chars — Urdu model context limit


def _extract_email_profile(raw_profile):
    """
    Parse the raw EXTRACTION_PROMPT output and pull the four fields
    that matter most for an inquiry email: diagnosis, age, medications,
    and lab values. Falls back to 'not specified' if a field is missing.
    """
    wanted = {
        "PRIMARY DIAGNOSIS":   "not specified",
        "PATIENT AGE":         "not specified",
        "CURRENT MEDICATIONS": "not specified",
        "RECENT LAB VALUES":   "not specified",
        "DISEASE STABILITY":   "",   # from REASONING_PROMPT if present
    }
    for line in raw_profile.split("\n"):
        stripped = line.strip()
        for field in wanted:
            prefix = field + ":"
            if stripped.upper().startswith(prefix):
                val = stripped[len(prefix):].strip()
                if val and val.upper() != "NOT FOUND":
                    wanted[field] = val
                break

    parts = [
        f"Primary condition: {wanted['PRIMARY DIAGNOSIS']}",
        f"Patient age: {wanted['PATIENT AGE']}",
        f"Current medications: {wanted['CURRENT MEDICATIONS']}",
        f"Key lab values: {wanted['RECENT LAB VALUES']}",
    ]
    if wanted["DISEASE STABILITY"]:
        parts.append(f"Disease stability: {wanted['DISEASE STABILITY']}")

    return "\n".join(parts)


def generate_inquiry_email(patient_profile, trial_result):
    """
    Generate a professional inquiry email to the trial coordinator.

    patient_profile — raw_extraction string from profile_extractor.
    trial_result    — clean dict from matcher.match_patient_to_trial().

    The email is addressed to the real coordinator name and email from the
    API, and references the patient's specific condition, age, medications,
    and lab values rather than a raw blob of text.

    Returns the email as a plain string, or an 'ERROR: ...' string on failure.
    """
    try:
        # ── Build coordinator contact block ──────────────────────────────────
        name  = trial_result.get("contact_name",  "Trial Coordinator")
        email = trial_result.get("contact_email", "")
        phone = trial_result.get("contact_phone", "")

        contact_lines = [f"Name:  {name}"]
        if email and email not in ("", "see ClinicalTrials.gov"):
            contact_lines.append(f"Email: {email}")
        if phone and phone not in ("", "see ClinicalTrials.gov"):
            contact_lines.append(f"Phone: {phone}")
        contact_info = "\n".join(contact_lines)

        # ── Build targeted patient profile summary ───────────────────────────
        profile_summary = _extract_email_profile(patient_profile)

        # ── Call model ───────────────────────────────────────────────────────
        prompt = EMAIL_DRAFT_PROMPT.format(
            trial_title    = trial_result.get("trial_title", "Unknown Trial"),
            nct_id         = trial_result.get("nct_id",      "Unknown"),
            contact_info   = contact_info,
            reason         = trial_result.get("reason",      ""),
            patient_profile = profile_summary,
        )
        result = stream_response([{"role": "user", "content": prompt}])
        return result if result else "ERROR: Model returned an empty email draft."

    except Exception as e:
        return f"ERROR: Could not generate inquiry email: {e}"


def explain_in_urdu(results_text):
    """
    Translate and explain the matching results in simple Urdu.

    results_text — formatted results string from app._format_results().
    Returns Urdu text, or an 'ERROR: ...' string on failure.
    """
    if not results_text or not results_text.strip():
        return (
            "نتائج دستیاب نہیں ہیں۔ پہلے تجزیہ چلائیں۔\n"
            "(No results available. Please run the analysis first.)"
        )
    try:
        prompt = URDU_EXPLAIN_PROMPT.format(
            results_text=results_text[:_MAX_RESULTS_FOR_URDU]
        )
        result = stream_response([{"role": "user", "content": prompt}])
        return result if result else "ERROR: Model returned an empty Urdu explanation."
    except Exception as e:
        return f"ERROR: Could not generate Urdu explanation: {e}"
