import requests

_API_URL = "https://clinicaltrials.gov/api/v2/studies"
_TIMEOUT = 10  # seconds


def fetch_trials(condition_keyword, max_results=5):
    """
    Fetch up to max_results recruiting clinical trials for condition_keyword
    from the ClinicalTrials.gov v2 API.
    Returns a list of study dicts, or an empty list on any error.
    """
    params = {
        "query.cond": condition_keyword,
        "filter.overallStatus": "RECRUITING",
        "pageSize": max_results,
        "format": "json",
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
        print(f"[trial_fetcher] ERROR: ClinicalTrials.gov returned an HTTP error: {e}")
        return []
    except Exception as e:
        print(f"[trial_fetcher] ERROR: Unexpected error fetching trials: {e}")
        return []

    try:
        data = response.json()
    except Exception as e:
        print(f"[trial_fetcher] ERROR: Could not parse JSON response: {e}")
        return []

    studies = data.get("studies", [])
    print(f"[trial_fetcher] Fetched {len(studies)} trial(s) for: {condition_keyword!r}")
    return studies
