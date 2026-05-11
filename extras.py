from utils import stream_response
from prompts import EMAIL_DRAFT_PROMPT, URDU_EXPLAIN_PROMPT

_MAX_PROFILE_FOR_EMAIL = 800   # chars — keeps email prompt within memory budget
_MAX_RESULTS_FOR_URDU = 2500   # chars — Urdu model context limit


def draft_inquiry_email(patient_profile, trial_result):
    """
    Generate a professional inquiry email to the trial coordinator.

    trial_result must be a dict as returned by matcher.match_patient_to_trial().
    Returns the email as a plain string, or an 'ERROR: ...' string on failure.
    """
    try:
        contact_lines = []
        name = trial_result.get("contact_name", "")
        email = trial_result.get("contact_email", "")
        phone = trial_result.get("contact_phone", "")
        if name:
            contact_lines.append(f"Name:  {name}")
        if email and email != "see ClinicalTrials.gov":
            contact_lines.append(f"Email: {email}")
        if phone and phone != "see ClinicalTrials.gov":
            contact_lines.append(f"Phone: {phone}")
        if not contact_lines:
            contact_lines.append("Contact details available at ClinicalTrials.gov")
        contact_info = "\n".join(contact_lines)

        prompt = EMAIL_DRAFT_PROMPT.format(
            trial_title=trial_result.get("trial_title", "Unknown Trial"),
            nct_id=trial_result.get("nct_id", "Unknown"),
            contact_info=contact_info,
            reason=trial_result.get("reason", ""),
            patient_profile=patient_profile[:_MAX_PROFILE_FOR_EMAIL],
        )
        result = stream_response([{"role": "user", "content": prompt}])
        return result if result else "ERROR: Model returned an empty email draft."

    except Exception as e:
        return f"ERROR: Could not draft email: {e}"


def explain_in_urdu(results_text):
    """
    Translate and explain the matching results in simple Urdu.

    results_text should be the formatted results string from the main pipeline.
    Returns Urdu text as a string, or an 'ERROR: ...' string on failure.
    """
    if not results_text or not results_text.strip():
        return "نتائج دستیاب نہیں ہیں۔ پہلے تجزیہ چلائیں۔\n(No results available. Please run the analysis first.)"

    try:
        prompt = URDU_EXPLAIN_PROMPT.format(
            results_text=results_text[:_MAX_RESULTS_FOR_URDU]
        )
        result = stream_response([{"role": "user", "content": prompt}])
        return result if result else "ERROR: Model returned an empty Urdu explanation."

    except Exception as e:
        return f"ERROR: Could not generate Urdu explanation: {e}"
