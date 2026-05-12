import requests

_API_URL = "https://clinicaltrials.gov/api/v2/studies"
_TIMEOUT = 10  # seconds


def _extract_trial(study):
    """
    Convert a raw ClinicalTrials.gov study object into a clean, flat dict.
    Every field has a safe fallback — this never raises.
    """
    try:
        protocol      = study.get("protocolSection", {})
        id_mod        = protocol.get("identificationModule", {})
        design_mod    = protocol.get("designModule", {})
        eligibility_mod = protocol.get("eligibilityModule", {})
        contacts_mod  = protocol.get("contactsLocationsModule", {})
        sponsor_mod   = protocol.get("sponsorCollaboratorsModule", {})

        # ── Core identity ────────────────────────────────────────────────────
        title  = id_mod.get("briefTitle", "Unknown Trial")
        nct_id = id_mod.get("nctId", "Unknown ID")

        # ── Eligibility criteria ─────────────────────────────────────────────
        eligibility_criteria = eligibility_mod.get(
            "eligibilityCriteria", "No eligibility criteria available."
        )

        # ── Contact details (central contacts list, take first entry) ────────
        central_contacts = contacts_mod.get("centralContacts", [])
        if central_contacts:
            c = central_contacts[0]
            contact_name  = c.get("name", "Trial Coordinator")
            contact_phone = c.get("phone", "")
            contact_email = c.get("email", "")
        else:
            contact_name  = "Trial Coordinator"
            contact_phone = ""
            contact_email = ""

        # ── Location (first listed site) ─────────────────────────────────────
        locations = contacts_mod.get("locations", [])
        if locations:
            loc         = locations[0]
            facility_raw = loc.get("facility", "")
            # ClinicalTrials.gov API v2: facility is a plain string, not a dict
            if isinstance(facility_raw, dict):
                facility = facility_raw.get("name", "")
            else:
                facility = str(facility_raw) if facility_raw else ""
            city    = loc.get("city", "")
            country = loc.get("country", "")
            parts   = [p for p in (facility, city, country) if p]
            location = ", ".join(parts) if parts else "See ClinicalTrials.gov"
        else:
            location = "See ClinicalTrials.gov"

        # ── Phase ────────────────────────────────────────────────────────────
        phases = design_mod.get("phases", [])
        phase  = phases[0] if phases else "Not specified"

        # ── Sponsor ──────────────────────────────────────────────────────────
        sponsor = (
            sponsor_mod.get("leadSponsor", {}).get("name", "Unknown sponsor")
        )

        return {
            "title":               title,
            "nct_id":              nct_id,
            "eligibility_criteria": eligibility_criteria,
            "contact_name":        contact_name,
            "contact_phone":       contact_phone,
            "contact_email":       contact_email,
            "location":            location,
            "phase":               phase,
            "sponsor":             sponsor,
        }

    except Exception as e:
        print(f"[trial_fetcher] WARNING: Could not fully parse a trial object: {e}")
        # Minimal safe fallback
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
            "title":               title,
            "nct_id":              nct_id,
            "eligibility_criteria": "",
            "contact_name":        "Trial Coordinator",
            "contact_phone":       "",
            "contact_email":       "",
            "location":            "See ClinicalTrials.gov",
            "phase":               "Not specified",
            "sponsor":             "Unknown",
        }


def fetch_trials(condition_keyword, max_results=5):
    """
    Fetch up to max_results recruiting clinical trials for condition_keyword.
    Returns a list of clean trial dicts (see _extract_trial for field names).
    Returns an empty list on any error.
    """
    params = {
        "query.cond":          condition_keyword,
        "filter.overallStatus": "RECRUITING",
        "pageSize":            max_results,
        "format":              "json",
    }

    try:
        response = requests.get(_API_URL, params=params, timeout=_TIMEOUT)
        response.raise_for_status()
    except requests.exceptions.Timeout:
        print(
            "[trial_fetcher] ERROR: Request to ClinicalTrials.gov timed out. "
            "Check your internet connection."
        )
        return []
    except requests.exceptions.ConnectionError:
        print(
            "[trial_fetcher] ERROR: Cannot reach ClinicalTrials.gov. "
            "Check your internet connection."
        )
        return []
    except requests.exceptions.HTTPError as e:
        print(f"[trial_fetcher] ERROR: ClinicalTrials.gov returned HTTP error: {e}")
        return []
    except Exception as e:
        print(f"[trial_fetcher] ERROR: Unexpected error fetching trials: {e}")
        return []

    try:
        data = response.json()
    except Exception as e:
        print(f"[trial_fetcher] ERROR: Could not parse JSON response: {e}")
        return []

    raw_studies  = data.get("studies", [])
    clean_trials = [_extract_trial(s) for s in raw_studies]

    print(f"[trial_fetcher] Fetched {len(clean_trials)} trial(s) for: {condition_keyword!r}")
    return clean_trials
