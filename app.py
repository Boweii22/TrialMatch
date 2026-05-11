import requests
import gradio as gr

from profile_extractor import extract_patient_profile
from trial_fetcher import fetch_trials
from matcher import match_patient_to_trial

# ---------------------------------------------------------------------------
# Static HTML snippets
# ---------------------------------------------------------------------------

_INFO_HTML = """
<div style="background-color:#e3f2fd;border-left:4px solid #1976D2;
            padding:14px 18px;border-radius:6px;margin:8px 0 16px 0;">
  <strong>Privacy &amp; Safety</strong><br>
  Your medical records are processed entirely on <em>your own computer</em> and are never
  uploaded anywhere. The only external request is a single condition keyword sent to the
  public ClinicalTrials.gov database to find open studies.<br><br>
  <strong>This tool is for informational purposes only.</strong>
  Always consult a qualified physician before making any medical decisions or enrolling
  in a clinical trial.
</div>
"""

_DISCLAIMER_HTML = """
<p style="font-size:0.78em;color:#888;text-align:center;margin-top:20px;">
  TrialMatch does not provide medical advice, diagnosis, or treatment.
  It is a research aid only. Always seek guidance from a licensed healthcare professional
  regarding any medical condition or clinical trial participation.
</p>
"""

# ---------------------------------------------------------------------------
# System check
# ---------------------------------------------------------------------------

def check_system():
    """Verify that Ollama is running and gemma3:4b is installed."""
    lines = []
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        resp.raise_for_status()
        lines.append("✓  Ollama is running")

        data = resp.json()
        installed = [m.get("name", "") for m in data.get("models", [])]
        if any("gemma3:4b" in name for name in installed):
            lines.append("✓  gemma3:4b model is installed — ready to run!")
        else:
            lines.append("✗  gemma3:4b model is NOT installed")
            lines.append("   Fix: open a terminal and run:   ollama pull gemma3:4b")
            if installed:
                lines.append(f"   Models currently installed: {', '.join(installed)}")
            else:
                lines.append("   No models are currently installed.")
    except requests.exceptions.ConnectionError:
        lines.append("✗  Ollama is NOT running")
        lines.append("   Fix: open a terminal and run:   ollama serve")
        lines.append("   Then click this button again.")
    except Exception as e:
        lines.append(f"✗  Could not check Ollama status: {e}")

    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_trialmatch(pdf_file, condition):
    """
    Generator function — yields (status, results) tuples so Gradio streams
    live progress without appearing to hang on slow CPU inference.
    """

    # --- Input validation ---
    if pdf_file is None:
        yield "Please upload a PDF file.", ""
        return

    if not condition or not condition.strip():
        yield "Please enter a condition keyword (e.g. 'type 2 diabetes').", ""
        return

    condition = condition.strip()

    # Resolve the PDF path from whatever Gradio version passes us
    if isinstance(pdf_file, str):
        pdf_path = pdf_file
    elif hasattr(pdf_file, "name"):
        pdf_path = pdf_file.name
    elif isinstance(pdf_file, dict):
        pdf_path = pdf_file.get("path") or pdf_file.get("name") or ""
    else:
        pdf_path = str(pdf_file)

    if not pdf_path:
        yield "ERROR: Could not determine the uploaded file path.", ""
        return

    # --- Step 1: Extract patient profile ---
    yield (
        "Step 1/3 — Reading your medical records "
        "(this may take 2–3 minutes on first run while the model loads)...",
        "",
    )

    try:
        patient_profile = extract_patient_profile(pdf_path)
    except Exception as e:
        yield f"ERROR reading PDF: {e}", ""
        return

    if patient_profile.startswith("ERROR:"):
        yield patient_profile, ""
        return

    if not patient_profile.strip():
        yield "ERROR: No text could be extracted from the PDF.", ""
        return

    # --- Step 2: Fetch trials ---
    yield "Step 2/3 — Searching ClinicalTrials.gov for open recruiting trials...", ""

    try:
        trials = fetch_trials(condition)
    except Exception as e:
        yield f"ERROR fetching trials: {e}", ""
        return

    if not trials:
        yield (
            "Search complete.",
            (
                "No recruiting trials were found for this condition on ClinicalTrials.gov.\n\n"
                "Suggestions:\n"
                "• Try a broader keyword (e.g. 'diabetes' instead of 'type 2 diabetes')\n"
                "• Try an alternative name for the condition\n"
                "• Check your internet connection and try again"
            ),
        )
        return

    # --- Step 3: Match each trial ---
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

        display_title = trial_title[:72] + ("..." if len(trial_title) > 72 else "")
        yield (
            f"Step 3/3 — Matching trial {i + 1} of {total}:\n{display_title}",
            "",
        )

        try:
            result = match_patient_to_trial(patient_profile, trial)
            result_text = result.get("result", "")
            result_upper = result_text.upper()
            if "VERDICT: MATCH" in result_upper or "VERDICT: PARTIAL" in result_upper:
                matches.append(result)
        except Exception:
            pass  # silently skip trials that fail to process

    # --- Format output ---
    if not matches:
        yield (
            "Analysis complete.",
            (
                f"No qualifying trials found among the {total} reviewed.\n\n"
                "Suggestions:\n"
                "• Try a broader condition keyword\n"
                "• New trials open regularly — try again in a few days\n"
                "• Consult your doctor about trials they may know of"
            ),
        )
        return

    output_lines = [
        f"Found {len(matches)} potential match(es) out of {total} trial(s) reviewed.\n"
    ]
    for match in matches:
        output_lines.append("━" * 62)
        output_lines.append(f"Trial:  {match['trial_title']}")
        output_lines.append(f"NCT ID: {match['nct_id']}")
        output_lines.append(
            f"Link:   https://clinicaltrials.gov/study/{match['nct_id']}"
        )
        output_lines.append("")
        output_lines.append(match["result"])
        output_lines.append("")

    yield "Analysis complete.", "\n".join(output_lines)

# ---------------------------------------------------------------------------
# Gradio interface (compatible with Gradio 4.x and 5.x)
# ---------------------------------------------------------------------------

with gr.Blocks(title="TrialMatch") as demo:

    gr.Markdown("# TrialMatch")
    gr.Markdown(
        "### Find clinical trials you qualify for — privately, on your own computer"
    )
    gr.HTML(_INFO_HTML)

    with gr.Tabs():

        # ── Main analysis tab ──────────────────────────────────────────────
        with gr.Tab("Run Analysis"):
            with gr.Row():

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

                with gr.Column(scale=1):
                    gr.Markdown("#### Live Status")
                    status_box = gr.Textbox(
                        label="Status",
                        interactive=False,
                        lines=3,
                        placeholder="Status will appear here while the analysis runs...",
                    )
                    gr.Markdown("#### Results")
                    results_box = gr.Textbox(
                        label="Results",
                        interactive=False,
                        lines=22,
                        placeholder=(
                            "Matching results will appear here after the analysis "
                            "completes.\n\nNote: the first run may take several minutes "
                            "because the AI model must load into memory."
                        ),
                    )

            run_btn.click(
                fn=run_trialmatch,
                inputs=[pdf_input, condition_input],
                outputs=[status_box, results_box],
            )

        # ── System check tab ──────────────────────────────────────────────
        with gr.Tab("System Check"):
            gr.Markdown(
                "Click **Check System** to confirm that Ollama is running "
                "and that the `gemma3:4b` model is downloaded."
            )
            check_btn = gr.Button("Check System", variant="secondary")
            check_output = gr.Textbox(
                label="System Status",
                interactive=False,
                lines=8,
            )
            check_btn.click(
                fn=check_system,
                inputs=[],
                outputs=[check_output],
            )

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
