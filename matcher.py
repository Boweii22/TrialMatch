import ollama

from prompts import MATCHING_PROMPT

_MODEL = "gemma3:4b"
_MAX_ELIGIBILITY_CHARS = 1500


def match_patient_to_trial(patient_profile, trial):
    """
    Ask Gemma 4 whether patient_profile meets the eligibility criteria of trial.
    Returns a dict:
        {
            'trial_title': str,
            'nct_id':      str,
            'result':      str,   # VERDICT / REASON / NEXT STEP block, or ERROR string
        }
    Never raises — errors are captured in the 'result' field.
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
        )

        # Truncate to stay within memory limits on CPU-only hardware
        eligibility_text = eligibility_text[:_MAX_ELIGIBILITY_CHARS]

        prompt = MATCHING_PROMPT.format(
            patient_profile=patient_profile,
            eligibility_criteria=eligibility_text,
        )

        response_text = ""
        stream = ollama.chat(
            model=_MODEL,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
        )
        for chunk in stream:
            try:
                content = chunk.message.content
                if content:
                    response_text += content
            except AttributeError:
                try:
                    content = chunk["message"]["content"]
                    if content:
                        response_text += content
                except (KeyError, TypeError):
                    pass

        result = response_text.strip() if response_text.strip() else "ERROR: Model returned an empty response."

        return {"trial_title": title, "nct_id": nct_id, "result": result}

    except Exception as e:
        return {
            "trial_title": title,
            "nct_id": nct_id,
            "result": f"ERROR: Could not process this trial. {e}",
        }
