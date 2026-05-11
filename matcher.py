import re

from utils import stream_response
from prompts import MATCHING_PROMPT, DISQUALIFIER_PROMPT

_MAX_ELIGIBILITY_CHARS = 1500


def _parse_match_response(text):
    """Extract structured fields from a MATCHING_PROMPT response."""
    parsed = {
        "verdict": "UNKNOWN",
        "confidence": 50,
        "reason": text.strip(),
        "disqualifiers": "NONE",
        "next_step": "",
    }
    for line in text.split("\n"):
        line = line.strip()
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
                parsed["confidence"] = min(100, max(0, int(nums[0])))
        elif upper.startswith("REASON:"):
            parsed["reason"] = line[7:].strip()
        elif upper.startswith("DISQUALIFIERS:"):
            parsed["disqualifiers"] = line[14:].strip()
        elif upper.startswith("NEXT STEP:"):
            parsed["next_step"] = line[10:].strip()
    return parsed


def _get_contact_info(trial):
    """Pull coordinator contact details from a ClinicalTrials.gov study dict."""
    try:
        contacts = (
            trial.get("protocolSection", {})
            .get("contactsLocationsModule", {})
            .get("centralContacts", [])
        )
        if contacts:
            c = contacts[0]
            return {
                "contact_name": c.get("name", "Trial Coordinator"),
                "contact_email": c.get("email", "see ClinicalTrials.gov"),
                "contact_phone": c.get("phone", "see ClinicalTrials.gov"),
            }
    except Exception:
        pass
    return {
        "contact_name": "Trial Coordinator",
        "contact_email": "see ClinicalTrials.gov",
        "contact_phone": "see ClinicalTrials.gov",
    }


def match_patient_to_trial(patient_profile, clinical_reasoning, trial):
    """
    Match a patient to a single trial.

    For NO/PARTIAL verdicts also runs DISQUALIFIER_PROMPT to cite exact
    criteria lines the patient fails — shown in the UI as detailed analysis.

    Returns a dict with keys:
        trial_title, nct_id, verdict, confidence, reason, disqualifiers,
        next_step, disqualifier_detail, contact_name, contact_email,
        contact_phone, raw_result
    """
    title = "Unknown Trial"
    nct_id = "Unknown ID"

    try:
        protocol = trial.get("protocolSection", {})
        id_module = protocol.get("identificationModule", {})
        eligibility_module = protocol.get("eligibilityModule", {})

        title = id_module.get("briefTitle", "Unknown Trial")
        nct_id = id_module.get("nctId", "Unknown ID")
        eligibility_text = eligibility_module.get(
            "eligibilityCriteria", "No eligibility criteria available."
        )[:_MAX_ELIGIBILITY_CHARS]

        contact_info = _get_contact_info(trial)

        # ── Primary matching ────────────────────────────────────────────────
        prompt = MATCHING_PROMPT.format(
            patient_profile=patient_profile,
            clinical_reasoning=clinical_reasoning,
            eligibility_criteria=eligibility_text,
        )
        raw = stream_response([{"role": "user", "content": prompt}])
        parsed = _parse_match_response(raw)

        # ── Disqualifier detail for NO / PARTIAL ────────────────────────────
        disqualifier_detail = ""
        if parsed["verdict"] in ("NO", "PARTIAL"):
            print(f"[matcher] Running disqualifier analysis for verdict={parsed['verdict']}...")
            try:
                dq_prompt = DISQUALIFIER_PROMPT.format(
                    patient_profile=patient_profile,
                    eligibility_criteria=eligibility_text,
                    verdict=parsed["verdict"],
                )
                disqualifier_detail = stream_response(
                    [{"role": "user", "content": dq_prompt}]
                )
            except Exception as e:
                disqualifier_detail = f"[detailed analysis unavailable: {e}]"

        return {
            "trial_title": title,
            "nct_id": nct_id,
            "verdict": parsed["verdict"],
            "confidence": parsed["confidence"],
            "reason": parsed["reason"],
            "disqualifiers": parsed["disqualifiers"],
            "next_step": parsed["next_step"],
            "disqualifier_detail": disqualifier_detail,
            "raw_result": raw,
            **contact_info,
        }

    except Exception as e:
        return {
            "trial_title": title,
            "nct_id": nct_id,
            "verdict": "ERROR",
            "confidence": 0,
            "reason": f"Could not process this trial: {e}",
            "disqualifiers": "",
            "next_step": "",
            "disqualifier_detail": "",
            "raw_result": f"ERROR: {e}",
            "contact_name": "Unknown",
            "contact_email": "",
            "contact_phone": "",
        }
