#!/usr/bin/env python3
"""
One-time setup script — run this once with internet to build the local
trials database. After that, TrialMatch works fully offline.

Usage:
    python download_trials_db.py

Time: ~2-3 minutes. Output: trials_db.json (~3-5 MB)
"""
import json
import os
import time

import requests

_API_URL        = "https://clinicaltrials.gov/api/v2/studies"
_DB_PATH        = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trials_db.json")
_PER_CONDITION  = 100   # trials per condition (API max per page is 1000)
_REQUEST_DELAY  = 0.4   # seconds between API calls — polite rate limiting

SEED_CONDITIONS = [
    # Metabolic
    "type 2 diabetes", "type 1 diabetes", "obesity",
    # Cancer
    "lung cancer", "breast cancer", "prostate cancer", "colorectal cancer",
    "ovarian cancer", "leukemia", "lymphoma", "melanoma", "pancreatic cancer",
    # Cardiovascular
    "heart failure", "coronary artery disease", "atrial fibrillation",
    "hypertension", "stroke",
    # Respiratory
    "COPD", "asthma", "pulmonary fibrosis",
    # Neurological
    "Alzheimer disease", "Parkinson disease", "multiple sclerosis",
    "epilepsy", "amyotrophic lateral sclerosis",
    # Autoimmune / inflammatory
    "rheumatoid arthritis", "lupus", "Crohn disease", "ulcerative colitis",
    "psoriasis",
    # Infectious
    "HIV", "hepatitis B", "hepatitis C", "tuberculosis",
    # Renal
    "chronic kidney disease",
    # Mental health
    "depression", "anxiety", "schizophrenia", "bipolar disorder",
    # Rare / paediatric
    "sickle cell disease", "cystic fibrosis",
]


def _extract_trial(study):
    """Extract clean flat dict from a raw ClinicalTrials.gov study object."""
    try:
        protocol        = study.get("protocolSection", {})
        id_mod          = protocol.get("identificationModule", {})
        design_mod      = protocol.get("designModule", {})
        eligibility_mod = protocol.get("eligibilityModule", {})
        contacts_mod    = protocol.get("contactsLocationsModule", {})
        sponsor_mod     = protocol.get("sponsorCollaboratorsModule", {})
        status_mod      = protocol.get("statusModule", {})
        conditions_mod  = protocol.get("conditionsModule", {})

        title      = id_mod.get("briefTitle", "Unknown Trial")
        nct_id     = id_mod.get("nctId", "Unknown ID")
        conditions = conditions_mod.get("conditions", [])

        eligibility_criteria = eligibility_mod.get(
            "eligibilityCriteria", "No eligibility criteria available."
        )

        central_contacts = contacts_mod.get("centralContacts", [])
        if central_contacts:
            c             = central_contacts[0]
            contact_name  = c.get("name",  "Trial Coordinator")
            contact_phone = c.get("phone", "")
            contact_email = c.get("email", "")
        else:
            contact_name, contact_phone, contact_email = "Trial Coordinator", "", ""

        locations = contacts_mod.get("locations", [])
        if locations:
            loc          = locations[0]
            facility_raw = loc.get("facility", "")
            facility     = (facility_raw.get("name", "")
                            if isinstance(facility_raw, dict)
                            else str(facility_raw or ""))
            city    = loc.get("city",    "")
            country = loc.get("country", "")
            parts   = [p for p in (facility, city, country) if p]
            location = ", ".join(parts) if parts else "See ClinicalTrials.gov"
        else:
            location = "See ClinicalTrials.gov"

        completion_date = status_mod.get("primaryCompletionDate", {}).get("date", "")
        phases  = design_mod.get("phases", [])
        phase   = phases[0] if phases else "Not specified"
        sponsor = sponsor_mod.get("leadSponsor", {}).get("name", "Unknown sponsor")

        return {
            "title":                title,
            "nct_id":               nct_id,
            "conditions":           conditions,
            "eligibility_criteria": eligibility_criteria,
            "contact_name":         contact_name,
            "contact_phone":        contact_phone,
            "contact_email":        contact_email,
            "location":             location,
            "phase":                phase,
            "sponsor":              sponsor,
            "completion_date":      completion_date,
        }
    except Exception as e:
        print(f"  WARNING: parse error on a trial — {e}")
        return None


def _fetch_for_condition(condition, per_condition):
    params = {
        "query.cond":           condition,
        "filter.overallStatus": "RECRUITING",
        "pageSize":             per_condition,
        "format":               "json",
    }
    try:
        r = requests.get(_API_URL, params=params, timeout=20)
        r.raise_for_status()
        studies = r.json().get("studies", [])
        return [t for s in studies if (t := _extract_trial(s))]
    except Exception as e:
        print(f"  ERROR: {e}")
        return []


def build_database():
    """
    Generator — yields one progress string per step.
    Used by the first-launch auto-setup in app.py.
    """
    total = len(SEED_CONDITIONS)
    yield f"Downloading trial database ({total} condition categories, up to {_PER_CONDITION} trials each)..."

    all_trials = {}   # keyed by nct_id — automatic deduplication

    for i, condition in enumerate(SEED_CONDITIONS, 1):
        yield f"  [{i:2}/{total}] {condition}..."
        trials = _fetch_for_condition(condition, _PER_CONDITION)
        for t in trials:
            all_trials[t["nct_id"]] = t
        time.sleep(_REQUEST_DELAY)

    with open(_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(list(all_trials.values()), f, ensure_ascii=False, separators=(",", ":"))

    size_mb = os.path.getsize(_DB_PATH) / (1024 * 1024)
    yield f"Done. {len(all_trials)} unique trials saved ({size_mb:.1f} MB). TrialMatch is ready."


if __name__ == "__main__":
    print("TrialMatch — building offline trials database")
    for line in build_database():
        print(line)
