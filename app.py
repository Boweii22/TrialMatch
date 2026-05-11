import requests
import gradio as gr

from profile_extractor import extract_patient_profile
from trial_fetcher import fetch_trials
from matcher import match_patient_to_trial
from extras import draft_inquiry_email, explain_in_urdu

# ---------------------------------------------------------------------------
# Static HTML
# ---------------------------------------------------------------------------

_INFO_HTML = """
<div style="background-color:#e3f2fd;border-left:4px solid #1976D2;
            padding:14px 18px;border-radius:6px;margin:8px 0 16px 0;">
  <strong>Privacy &amp; Safety</strong><br>
  Your medical records are processed entirely on <em>your own computer</em> and never
  leave it. The only external request is a single condition keyword sent to the public
  ClinicalTrials.gov database.<br><br>
  <strong>For informational purposes only.</strong>
  Always consult a qualified physician before making any medical decisions.
</div>
"""

_DISCLAIMER_HTML = """
<p style="font-size:0.78em;color:#888;text-align:center;margin-top:20px;">
  TrialMatch does not provide medical advice, diagnosis, or treatment.
  It is a research aid only. Always seek guidance from a licensed healthcare professional.
</p>
"""

# ---------------------------------------------------------------------------
# Result formatter
# ---------------------------------------------------------------------------

def _format_results(matches, total_trials, key_flags=None):
    lines = []
    if key_flags:
        lines += ["── Clinical Profile Summary ────────────────────────────────"]
        for flag in key_flags:
            lines.append(f"  • {flag}")
        lines.append("")
    lines.append(f"Found {len(matches)} potential match(es) out of {total_trials} trial(s) reviewed.\n")
    for m in matches:
        verdict = m["verdict"]
        conf = m["confidence"]

        if verdict == "MATCH":
            label = f"MATCH  |  Confidence: {conf}/100"
        elif verdict == "PARTIAL":
            label = f"PARTIAL MATCH  |  Confidence: {conf}/100"
        else:
            label = verdict

        lines += [
            "━" * 64,
            f"Trial:     {m['trial_title']}",
            f"NCT ID:    {m['nct_id']}",
            f"Link:      https://clinicaltrials.gov/study/{m['nct_id']}",
            "",
            f"VERDICT:   {label}",
            f"REASON:    {m['reason']}",
        ]

        dq = m.get("disqualifiers", "")
        if dq and dq.upper() not in ("NONE", ""):
            lines.append(f"DISQUALIFIERS: {dq}")

        ns = m.get("next_step", "")
        if ns:
            lines.append(f"NEXT STEP: {ns}")

        detail = m.get("disqualifier_detail", "")
        if detail:
            lines += ["", "── Detailed Eligibility Analysis ──────────────────────", detail]

        contact_name = m.get("contact_name", "")
        contact_email = m.get("contact_email", "")
        contact_phone = m.get("contact_phone", "")
        if any(v and v != "see ClinicalTrials.gov" for v in (contact_name, contact_email, contact_phone)):
            lines.append("")
            lines.append("── Trial Contact ───────────────────────────────────────")
            if contact_name:
                lines.append(f"  Name:  {contact_name}")
            if contact_email and contact_email != "see ClinicalTrials.gov":
                lines.append(f"  Email: {contact_email}")
            if contact_phone and contact_phone != "see ClinicalTrials.gov":
                lines.append(f"  Phone: {contact_phone}")

        lines.append("")

    return "\n".join(lines)

# ---------------------------------------------------------------------------
# System check
# ---------------------------------------------------------------------------

def check_system():
    from utils import MODEL
    lines = []
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        resp.raise_for_status()
        lines.append("✓  Ollama is running")
        installed = [m.get("name", "") for m in resp.json().get("models", [])]
        if any(MODEL in name for name in installed):
            lines.append(f"✓  {MODEL} is installed — ready to run!")
        else:
            lines.append(f"✗  {MODEL} is NOT installed")
            lines.append(f"   Fix: open a terminal and run:   ollama pull {MODEL}")
            if installed:
                lines.append(f"   Models currently installed: {', '.join(installed)}")
    except requests.exceptions.ConnectionError:
        lines.append("✗  Ollama is NOT running")
        lines.append("   Fix: open a terminal and run:   ollama serve")
    except Exception as e:
        lines.append(f"✗  Could not check Ollama status: {e}")
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Main pipeline  (yields 3 outputs: status, results, emails)
# ---------------------------------------------------------------------------

def run_trialmatch(pdf_file, condition):
    """
    Generator — yields (status, results, emails) tuples so Gradio can stream
    live progress updates to all three output boxes simultaneously.
    """

    # ── Validate inputs ─────────────────────────────────────────────────────
    if pdf_file is None:
        yield "Please upload a PDF file.", "", ""
        return
    if not condition or not condition.strip():
        yield "Please enter a condition keyword (e.g. 'type 2 diabetes').", "", ""
        return

    condition = condition.strip()

    if isinstance(pdf_file, str):
        pdf_path = pdf_file
    elif hasattr(pdf_file, "name"):
        pdf_path = pdf_file.name
    elif isinstance(pdf_file, dict):
        pdf_path = pdf_file.get("path") or pdf_file.get("name") or ""
    else:
        pdf_path = str(pdf_file)

    if not pdf_path:
        yield "ERROR: Could not determine the uploaded file path.", "", ""
        return

    # ── Step 1: Extract profile + clinical reasoning ─────────────────────────
    yield (
        "Step 1/3 — Reading your medical records and running clinical reasoning...\n"
        "(first run may take 2–3 minutes while the model loads)",
        "", "",
    )

    try:
        profile_data = extract_patient_profile(pdf_path)
    except Exception as e:
        yield f"ERROR reading PDF: {e}", "", ""
        return

    if isinstance(profile_data, str):          # error string returned
        yield profile_data, "", ""
        return

    patient_profile = profile_data["raw_extraction"]
    clinical_reasoning = profile_data["clinical_reasoning"]
    key_flags = profile_data["key_flags"]

    # ── Step 2: Fetch trials ─────────────────────────────────────────────────
    yield "Step 2/3 — Searching ClinicalTrials.gov for open recruiting trials...", "", ""

    try:
        trials = fetch_trials(condition)
    except Exception as e:
        yield f"ERROR fetching trials: {e}", "", ""
        return

    if not trials:
        yield (
            "Search complete.",
            (
                "No recruiting trials found for this condition.\n\n"
                "Suggestions:\n"
                "• Try a broader keyword (e.g. 'diabetes' instead of 'type 2 diabetes')\n"
                "• Try an alternative name for the condition\n"
                "• Check your internet connection and try again"
            ),
            "",
        )
        return

    # ── Step 3: Match each trial ─────────────────────────────────────────────
    matches = []
    total = len(trials)

    for i, trial in enumerate(trials):
        try:
            trial_title = (
                trial.get("protocolSection", {})
                .get("identificationModule", {})
                .get("briefTitle", f"Trial {i + 1}")
            )
        except Exception:
            trial_title = f"Trial {i + 1}"

        short = trial_title[:72] + ("..." if len(trial_title) > 72 else "")
        yield f"Step 3/3 — Matching trial {i + 1} of {total}:\n{short}", "", ""

        try:
            result = match_patient_to_trial(patient_profile, clinical_reasoning, trial)
            if result["verdict"] in ("MATCH", "PARTIAL"):
                matches.append(result)
        except Exception:
            pass

    # ── No matches ───────────────────────────────────────────────────────────
    if not matches:
        yield (
            "Analysis complete.",
            (
                f"No qualifying trials found among {total} reviewed.\n\n"
                "Suggestions:\n"
                "• Try a broader condition keyword\n"
                "• New trials open regularly — try again in a few days\n"
                "• Consult your doctor about trials they may know of"
            ),
            "",
        )
        return

    # ── Format results ───────────────────────────────────────────────────────
    results_text = _format_results(matches, total, key_flags)

    # ── Draft emails for MATCH verdicts ──────────────────────────────────────
    match_only = [m for m in matches if m["verdict"] == "MATCH"]
    if match_only:
        yield "Drafting inquiry emails for MATCH verdicts...", results_text, ""
        email_parts = []
        for m in match_only:
            print(f"[app] Drafting email for: {m['trial_title'][:50]}...")
            try:
                email_text = draft_inquiry_email(patient_profile, m)
                email_parts.append(
                    f"{'─' * 64}\nTrial: {m['trial_title']}\nNCT:   {m['nct_id']}\n\n{email_text}"
                )
            except Exception as e:
                email_parts.append(f"Could not draft email for {m['trial_title']}: {e}")
        emails_text = "\n\n".join(email_parts)
    else:
        emails_text = (
            "No full MATCH verdicts — only PARTIAL matches found.\n"
            "Emails are drafted for MATCH verdicts only.\n"
            "For PARTIAL matches, consult your doctor before reaching out to trial coordinators."
        )

    yield "Analysis complete.", results_text, emails_text

# ---------------------------------------------------------------------------
# Gradio UI
# ---------------------------------------------------------------------------

with gr.Blocks(title="TrialMatch") as demo:

    gr.Markdown("# TrialMatch")
    gr.Markdown("### Find clinical trials you qualify for — privately, on your own computer")
    gr.HTML(_INFO_HTML)

    with gr.Tabs():

        # ── Run Analysis tab ───────────────────────────────────────────────
        with gr.Tab("Run Analysis"):
            with gr.Row():

                # Left: inputs
                with gr.Column(scale=1):
                    gr.Markdown("#### Inputs")
                    pdf_input = gr.File(
                        label="Step 1 — Upload Medical Records (PDF)",
                        file_types=[".pdf"],
                        type="filepath",
                    )
                    condition_input = gr.Textbox(
                        label="Step 2 — Primary Condition Keyword",
                        placeholder="e.g. type 2 diabetes, lung cancer, breast cancer",
                        lines=1,
                    )
                    run_btn = gr.Button("▶  Run TrialMatch", variant="primary")

                # Right: outputs
                with gr.Column(scale=1):
                    gr.Markdown("#### Live Status")
                    status_box = gr.Textbox(
                        label="Status",
                        interactive=False,
                        lines=3,
                        placeholder="Status updates will appear here...",
                    )

                    gr.Markdown("#### Matching Results")
                    results_box = gr.Textbox(
                        label="Results",
                        interactive=False,
                        lines=20,
                        placeholder=(
                            "Results will appear here after analysis completes.\n\n"
                            "First run may take several minutes while the model loads."
                        ),
                    )

                    with gr.Accordion("📧  Draft Inquiry Emails  (generated for MATCH verdicts)", open=False):
                        email_box = gr.Textbox(
                            label="Email Drafts",
                            interactive=False,
                            lines=18,
                            placeholder="Email drafts will appear here after analysis completes.",
                        )

                    with gr.Accordion("🌐  اردو وضاحت — Explain in Urdu", open=False):
                        gr.Markdown(
                            "Click the button below to get a plain-Urdu explanation of the results "
                            "for patients who cannot read English."
                        )
                        urdu_btn = gr.Button("اردو میں سمجھائیں  (Explain in Urdu)", variant="secondary")
                        urdu_box = gr.Textbox(
                            label="Urdu Explanation",
                            interactive=False,
                            lines=18,
                            placeholder="اردو وضاحت یہاں ظاہر ہوگی...",
                        )

            # Wire up events
            run_btn.click(
                fn=run_trialmatch,
                inputs=[pdf_input, condition_input],
                outputs=[status_box, results_box, email_box],
            )

            urdu_btn.click(
                fn=explain_in_urdu,
                inputs=[results_box],
                outputs=[urdu_box],
            )

        # ── System Check tab ───────────────────────────────────────────────
        with gr.Tab("System Check"):
            gr.Markdown(
                "Click **Check System** to verify that Ollama is running "
                "and that the `gemma3:4b` model is installed."
            )
            check_btn = gr.Button("Check System", variant="secondary")
            check_output = gr.Textbox(label="System Status", interactive=False, lines=8)
            check_btn.click(fn=check_system, inputs=[], outputs=[check_output])

    gr.HTML(_DISCLAIMER_HTML)


if __name__ == "__main__":
    print("Starting TrialMatch — open http://127.0.0.1:7860 in your browser")
    demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        share=False,
        inbrowser=False,
        theme=gr.themes.Soft(),
    )
