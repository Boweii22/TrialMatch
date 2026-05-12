from utils import TOKENS, stream_response
from prompts import EMAIL_DRAFT_PROMPT, URDU_EXPLAIN_PROMPT, TRANSLATION_PROMPT

_TRANSLATABLE_FIELDS = ("reason", "next_step", "disqualifiers")
_LANGUAGES = ("English", "Urdu", "Arabic", "French")


def translate_matches(matches, language):
    """
    Translate only the plain-English explanation fields (reason, next_step,
    disqualifiers) in each match dict. Trial titles, NCT IDs, medical codes,
    and all other fields are left untouched.

    Uses one LLM call per match (batched fields) to minimise CPU time.
    Returns a new list of dicts with translated fields.
    """
    if language == "English" or not matches:
        return matches

    translated = []
    for i, m in enumerate(matches):
        print(f"[extras] Translating match {i + 1} of {len(matches)} to {language}...")
        tm = dict(m)  # shallow copy — only mutate the three fields below

        reason        = m.get("reason", "")
        next_step     = m.get("next_step", "")
        disqualifiers = m.get("disqualifiers", "NONE")

        # Build a batched text block with labelled fields
        batch_lines = []
        if reason:
            batch_lines.append(f"REASON: {reason}")
        if next_step:
            batch_lines.append(f"NEXT STEP: {next_step}")
        if disqualifiers and disqualifiers.upper() not in ("NONE", ""):
            batch_lines.append(f"DISQUALIFIERS: {disqualifiers}")

        if not batch_lines:
            translated.append(tm)
            continue

        try:
            prompt = TRANSLATION_PROMPT.format(
                language=language,
                text="\n".join(batch_lines),
            )
            out = stream_response([{"role": "user", "content": prompt}], max_tokens=TOKENS["translate"])

            # Parse translated fields back by their preserved English labels
            for line in out.split("\n"):
                line = line.strip()
                upper = line.upper()
                if upper.startswith("REASON:"):
                    tm["reason"] = line[7:].strip()
                elif upper.startswith("NEXT STEP:"):
                    tm["next_step"] = line[10:].strip()
                elif upper.startswith("DISQUALIFIERS:"):
                    tm["disqualifiers"] = line[14:].strip()

        except Exception as e:
            print(f"[extras] Translation failed for match {i + 1}: {e}")
            # Keep original English fields on failure

        translated.append(tm)

    return translated

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
        result = stream_response([{"role": "user", "content": prompt}], max_tokens=TOKENS["email"])
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
        result = stream_response([{"role": "user", "content": prompt}], max_tokens=TOKENS["urdu"])
        return result if result else "ERROR: Model returned an empty Urdu explanation."
    except Exception as e:
        return f"ERROR: Could not generate Urdu explanation: {e}"
