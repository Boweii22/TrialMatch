import json
import os

import requests

_API_URL = "https://clinicaltrials.gov/api/v2/studies"
_TIMEOUT = 10

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trials_db.json")


def db_exists():
    return os.path.exists(DB_PATH)


def _extract_trial(study):
    """
    Convert a raw ClinicalTrials.gov study object into a clean, flat dict.
    Every field has a safe fallback — this never raises.
    """
    try:
        protocol        = study.get("protocolSection", {})
        id_mod          = protocol.get("identificationModule", {})
        design_mod      = protocol.get("designModule", {})
        eligibility_mod = protocol.get("eligibilityModule", {})
        contacts_mod    = protocol.get("contactsLocationsModule", {})
        sponsor_mod     = protocol.get("sponsorCollaboratorsModule", {})
        status_mod      = protocol.get("statusModule", {})
        conditions_mod  = protocol.get("conditionsModule", {})

        # ── Core identity ────────────────────────────────────────────────────
        title      = id_mod.get("briefTitle", "Unknown Trial")
        nct_id     = id_mod.get("nctId",      "Unknown ID")
        conditions = conditions_mod.get("conditions", [])

        # ── Eligibility criteria ─────────────────────────────────────────────
        eligibility_criteria = eligibility_mod.get(
            "eligibilityCriteria", "No eligibility criteria available."
        )

        # ── Contact details ──────────────────────────────────────────────────
        central_contacts = contacts_mod.get("centralContacts", [])
        if central_contacts:
            c             = central_contacts[0]
            contact_name  = c.get("name",  "Trial Coordinator")
            contact_phone = c.get("phone", "")
            contact_email = c.get("email", "")
        else:
            contact_name, contact_phone, contact_email = "Trial Coordinator", "", ""

        # ── Location (first listed site) ─────────────────────────────────────
        locations = contacts_mod.get("locations", [])
        if locations:
            loc          = locations[0]
            facility_raw = loc.get("facility", "")
            if isinstance(facility_raw, dict):
                facility = facility_raw.get("name", "")
            else:
                facility = str(facility_raw) if facility_raw else ""
            city    = loc.get("city",    "")
            country = loc.get("country", "")
            parts   = [p for p in (facility, city, country) if p]
            location = ", ".join(parts) if parts else "See ClinicalTrials.gov"
        else:
            location = "See ClinicalTrials.gov"

        # ── Estimated completion date ────────────────────────────────────────
        completion_date = (
            status_mod.get("primaryCompletionDate", {}).get("date", "")
        )

        # ── Phase ────────────────────────────────────────────────────────────
        phases = design_mod.get("phases", [])
        phase  = phases[0] if phases else "Not specified"

        # ── Sponsor ──────────────────────────────────────────────────────────
        sponsor = (
            sponsor_mod.get("leadSponsor", {}).get("name", "Unknown sponsor")
        )

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
        print(f"[trial_fetcher] WARNING: Could not fully parse a trial object: {e}")
        try:
            nct_id = (study.get("protocolSection", {})
                          .get("identificationModule", {})
                          .get("nctId", "Unknown"))
            title  = (study.get("protocolSection", {})
                          .get("identificationModule", {})
                          .get("briefTitle", "Unknown Trial"))
        except Exception:
            nct_id, title = "Unknown", "Unknown Trial"

        return {
            "title":                title,
            "nct_id":               nct_id,
            "conditions":           [],
            "eligibility_criteria": "",
            "contact_name":         "Trial Coordinator",
            "contact_phone":        "",
            "contact_email":        "",
            "location":             "See ClinicalTrials.gov",
            "phase":                "Not specified",
            "sponsor":              "Unknown",
            "completion_date":      "",
        }


def _score_trial(trial, kw_lower, kw_words):
    """
    Score how well a trial matches a condition keyword.
    3 — keyword found in a structured condition tag  (most authoritative)
    2 — all keyword words found in trial title
    1 — keyword found in eligibility criteria text
    0 — no match
    """
    for cond in trial.get("conditions", []):
        if kw_lower in cond.lower():
            return 3
    title_lower = trial.get("title", "").lower()
    if kw_words and all(w in title_lower for w in kw_words):
        return 2
    if any(w in title_lower for w in kw_words):
        return 1
    if kw_lower in trial.get("eligibility_criteria", "").lower():
        return 1
    return 0


def _fetch_trials_offline(condition_keyword, max_results):
    """Search trials_db.json — no internet required."""
    try:
        with open(DB_PATH, encoding="utf-8") as f:
            all_trials = json.load(f)
    except Exception as e:
        print(f"[trial_fetcher] WARNING: Could not read local DB: {e}")
        return None   # signal caller to fall back to online

    kw_lower = condition_keyword.lower().strip()
    kw_words = [w for w in kw_lower.split() if len(w) > 2]

    scored = [(s, t) for t in all_trials if (s := _score_trial(t, kw_lower, kw_words)) > 0]
    scored.sort(key=lambda x: -x[0])
    results = [t for _, t in scored[:max_results]]

    print(f"[trial_fetcher] Offline: {len(results)} trial(s) for {condition_keyword!r} "
          f"(searched {len(all_trials)} local records)")
    return results


def fetch_trials(condition_keyword, max_results=3):
    """
    Return up to max_results recruiting trials for condition_keyword.

    Priority:
      1. Local trials_db.json  — instant, zero internet
      2. ClinicalTrials.gov API — fallback when DB not present
    """
    if db_exists():
        results = _fetch_trials_offline(condition_keyword, max_results)
        if results is not None:
            return results

    # ── Online fallback ───────────────────────────────────────────────────────
    print(f"[trial_fetcher] Online: querying ClinicalTrials.gov for {condition_keyword!r}")
    params = {
        "query.cond":           condition_keyword,
        "filter.overallStatus": "RECRUITING",
        "pageSize":             max_results,
        "format":               "json",
    }

    try:
        response = requests.get(_API_URL, params=params, timeout=_TIMEOUT)
        response.raise_for_status()
    except requests.exceptions.Timeout:
        print("[trial_fetcher] ERROR: Request timed out.")
        return []
    except requests.exceptions.ConnectionError:
        print("[trial_fetcher] ERROR: Cannot reach ClinicalTrials.gov.")
        return []
    except requests.exceptions.HTTPError as e:
        print(f"[trial_fetcher] ERROR: HTTP error: {e}")
        return []
    except Exception as e:
        print(f"[trial_fetcher] ERROR: {e}")
        return []

    try:
        data = response.json()
    except Exception as e:
        print(f"[trial_fetcher] ERROR: Could not parse JSON: {e}")
        return []

    raw_studies  = data.get("studies", [])
    clean_trials = [_extract_trial(s) for s in raw_studies]
    print(f"[trial_fetcher] Online: fetched {len(clean_trials)} trial(s)")
    return clean_trials
