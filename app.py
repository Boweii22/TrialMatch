import requests
import gradio as gr

from profile_extractor import extract_patient_profile
from trial_fetcher import fetch_trials
from matcher import match_patient_to_trial
from extras import generate_inquiry_email, translate_matches

_LANGUAGES = ["English", "Urdu", "Arabic", "French"]
_RTL_LANGUAGES = {"Urdu", "Arabic"}

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
# HTML helpers
# ---------------------------------------------------------------------------

def _msg_html(text, color="#444"):
    """Wrap a plain-text message in simple HTML for the gr.HTML results box."""
    safe  = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    paras = "".join(
        f"<p style='margin:4px 0;'>{l}</p>"
        for l in safe.split("\n") if l.strip()
    )
    return f'<div style="font-family:sans-serif;padding:10px;color:{color};">{paras}</div>'


def _confidence_bar_html(confidence, bar_color):
    """Render a coloured progress bar for a confidence score."""
    return (
        f'<div style="display:flex;align-items:center;gap:10px;margin:6px 0;">'
        f'  <div style="flex:1;background:#e0e0e0;border-radius:4px;height:13px;overflow:hidden;">'
        f'    <div style="width:{confidence}%;height:100%;background:{bar_color};border-radius:4px;"></div>'
        f'  </div>'
        f'  <span style="font-weight:bold;color:{bar_color};min-width:38px;">{confidence}%</span>'
        f'</div>'
    )


def _build_criterion_rows(match):
    """
    Parse disqualifier_detail to produce (criterion_text, status_label, text_color, row_bg)
    tuples for the breakdown table.
    MATCH verdict → two green "Met" rows.
    PARTIAL/NO    → failed/borderline rows parsed from DISQUALIFIER_PROMPT output.
    """
    verdict = match.get("verdict", "UNKNOWN")
    detail  = match.get("disqualifier_detail", "")
    dq_line = match.get("disqualifiers", "NONE")

    failed     = []
    borderline = []

    if detail:
        in_section = None
        for line in detail.split("\n"):
            s = line.strip()
            if not s:
                continue
            up = s.upper()
            if "FAILED CRITERIA:" in up:
                in_section = "failed"
            elif "BORDERLINE CRITERIA:" in up:
                in_section = "borderline"
            elif in_section and up not in ("NONE", ""):
                # Strip leading numbering / quotes; truncate after "— REASON:"
                text = s.lstrip("0123456789.-) ").strip("\"'")
                if "— REASON:" in text:
                    text = text.split("— REASON:")[0].strip().strip("\"'")
                if text and len(text) > 3 and "NONE" not in text.upper():
                    snippet = text[:72] + ("..." if len(text) > 72 else "")
                    if in_section == "failed":
                        failed.append(snippet)
                    else:
                        borderline.append(snippet)

    if verdict == "MATCH":
        return [
            ("All eligibility criteria reviewed", "✓  Met",           "#2e7d32", "#f1f8e9"),
            ("Exclusion criteria",                "✓  None triggered", "#2e7d32", "#f1f8e9"),
        ]

    rows = []
    for item in failed:
        rows.append((item, "✗  Failed",    "#c62828", "#ffebee"))
    for item in borderline:
        rows.append((item, "⚠  Borderline", "#e65100", "#fff3e0"))

    if not rows:
        # Fall back to the one-liner from MATCHING_PROMPT
        if dq_line and dq_line.upper() not in ("NONE", ""):
            dq_line = dq_line[:72]
        else:
            dq_line = "Requirements uncertain — manual review needed"
        color  = "#e65100" if verdict == "PARTIAL" else "#c62828"
        bg     = "#fff3e0" if verdict == "PARTIAL" else "#ffebee"
        status = "⚠  Borderline" if verdict == "PARTIAL" else "✗  Failed"
        rows.append((dq_line, status, color, bg))

    return rows


def _format_results_html(matches, total_trials, key_flags=None):
    """
    Rich HTML results block:
    - Sorted by confidence_score descending (highest first)
    - Colour-coded confidence bar: ≥80 green, 50–79 orange, <50 red
    - Per-trial criterion breakdown table
    """
    # Sort highest confidence first
    sorted_m = sorted(matches, key=lambda m: m.get("confidence_score", 0), reverse=True)

    parts = ['<div style="font-family:sans-serif;padding:4px;">']

    # Clinical profile summary banner
    if key_flags:
        items = "".join(f'<li style="margin:3px 0;">{f}</li>' for f in key_flags)
        parts.append(
            '<div style="background:#e8f5e9;border-left:3px solid #2e7d32;'
            'padding:12px 16px;border-radius:4px;margin-bottom:16px;">'
            '<strong>🩺 Clinical Profile Summary</strong>'
            f'<ul style="margin:8px 0 0 18px;">{items}</ul></div>'
        )

    parts.append(
        f'<p style="color:#555;margin-bottom:14px;">'
        f'Found <strong>{len(sorted_m)}</strong> potential match(es) out of '
        f'<strong>{total_trials}</strong> trial(s) reviewed — '
        f'sorted by confidence score.</p>'
    )

    for m in sorted_m:
        verdict = m["verdict"]
        conf    = m["confidence_score"]

        # Colour scheme
        if conf >= 80:
            bar_color = "#2e7d32"   # green
            banner_bg = "#e8f5e9"
        elif conf >= 50:
            bar_color = "#e65100"   # orange
            banner_bg = "#fff3e0"
        else:
            bar_color = "#c62828"   # red
            banner_bg = "#ffebee"

        verdict_icon = "✅" if verdict == "MATCH" else "⚠️" if verdict == "PARTIAL" else "❌"
        verdict_label = f"{verdict_icon} {verdict}"

        # Metadata line
        phase    = m.get("phase", "")
        sponsor  = m.get("sponsor", "")
        location = m.get("location", "")
        meta = " · ".join(
            v for v in (phase, sponsor, location)
            if v and v not in ("Not specified", "Unknown sponsor", "See ClinicalTrials.gov")
        )

        # Criterion breakdown table
        crit_rows = _build_criterion_rows(m)
        tbody = ""
        for criterion, status, txt_col, row_bg in crit_rows:
            tbody += (
                f'<tr style="background:{row_bg};">'
                f'<td style="padding:5px 10px;border:1px solid #e0e0e0;">{criterion}</td>'
                f'<td style="padding:5px 10px;border:1px solid #e0e0e0;text-align:center;'
                f'color:{txt_col};font-weight:bold;white-space:nowrap;">{status}</td>'
                f'</tr>'
            )
        table_html = (
            '<table style="width:100%;border-collapse:collapse;font-size:0.82em;margin:10px 0;">'
            '<thead><tr style="background:#f5f5f5;">'
            '<th style="padding:5px 10px;border:1px solid #e0e0e0;text-align:left;">Eligibility Criterion</th>'
            '<th style="padding:5px 10px;border:1px solid #e0e0e0;text-align:center;width:130px;">Status</th>'
            f'</tr></thead><tbody>{tbody}</tbody></table>'
        )

        # Contact block
        cn = m.get("contact_name",  "")
        ce = m.get("contact_email", "")
        cp = m.get("contact_phone", "")
        contact_items = []
        if cn: contact_items.append(f"<strong>{cn}</strong>")
        if ce and ce != "see ClinicalTrials.gov":
            contact_items.append(f'<a href="mailto:{ce}" style="color:#1565C0;">{ce}</a>')
        if cp and cp != "see ClinicalTrials.gov":
            contact_items.append(cp)
        contact_html = (
            f'<p style="margin:6px 0;font-size:0.85em;color:#555;">'
            f'📞 Contact: {" · ".join(contact_items)}</p>'
            if contact_items else ""
        )

        nct_id   = m["nct_id"]
        reason   = m.get("reason",    "")
        next_step = m.get("next_step", "")
        ns_html  = f'<p style="margin:8px 0;"><strong>Next Step:</strong> {next_step}</p>' if next_step else ""

        parts.append(f'''
<div style="border:1px solid #e0e0e0;border-radius:8px;padding:18px;margin:12px 0;
            background:#fff;box-shadow:0 1px 4px rgba(0,0,0,0.07);">

  <div style="font-weight:bold;font-size:1em;margin-bottom:3px;">{m["trial_title"]}</div>
  <div style="color:#666;font-size:0.82em;margin-bottom:12px;">
    NCT:&nbsp;<code>{nct_id}</code>
    {"&nbsp;·&nbsp;" + meta if meta else ""}
    &nbsp;|&nbsp;
    <a href="https://clinicaltrials.gov/study/{nct_id}" target="_blank"
       style="color:#1565C0;">View on ClinicalTrials.gov ↗</a>
  </div>

  <div style="background:{banner_bg};border-radius:6px;padding:10px 14px;margin-bottom:12px;">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:5px;">
      <span style="font-weight:bold;color:{bar_color};">{verdict_label}</span>
    </div>
    {_confidence_bar_html(conf, bar_color)}
  </div>

  <p style="margin:8px 0;"><strong>Reason:</strong> {reason}</p>

  {table_html}

  {ns_html}
  {contact_html}

</div>''')

    parts.append('</div>')
    return "".join(parts)


def _format_translated_html(matches, total_trials, language, key_flags=None):
    """HTML block with translated fields, dir=rtl for Urdu/Arabic."""
    is_rtl     = language in _RTL_LANGUAGES
    dir_attr   = 'dir="rtl"' if is_rtl else ''
    text_align = "right" if is_rtl else "left"

    parts = [f'<div style="font-family:sans-serif;" {dir_attr}>',
             f'<h3 style="color:#1565C0;margin-bottom:12px;">🌐 Translated Results — {language}</h3>']

    if key_flags:
        items = "".join(f'<li style="margin:3px 0;">{f}</li>' for f in key_flags)
        parts.append(
            f'<div style="background:#e8f4fd;padding:12px;border-radius:6px;margin:0 0 14px 0;">'
            f'<ul style="margin:6px 0 0 18px;">{items}</ul></div>'
        )

    parts.append(f'<p style="color:#555;margin-bottom:10px;">Found {len(matches)} of {total_trials} reviewed.</p>')

    for m in matches:
        verdict = m["verdict"]
        conf    = m["confidence_score"]
        color   = "#2e7d32" if verdict == "MATCH" else "#e65100" if verdict == "PARTIAL" else "#c62828"
        nct_id  = m.get("nct_id", "")
        reason  = m.get("reason", "")
        dq      = m.get("disqualifiers", "NONE")
        ns      = m.get("next_step", "")

        dq_block = (f'<p style="text-align:{text_align};margin:6px 0;">'
                    f'<strong>Disqualifiers:</strong> {dq}</p>'
                    if dq and dq.upper() not in ("NONE", "") else "")
        ns_block = (f'<p style="text-align:{text_align};margin:6px 0;">'
                    f'<strong>Next Step:</strong> {ns}</p>' if ns else "")

        parts.append(f'''
<div style="border:1px solid #e0e0e0;border-radius:8px;padding:16px;margin:10px 0;background:#fff;" {dir_attr}>
  <div style="font-weight:bold;margin-bottom:4px;">{m.get("trial_title","")}</div>
  <div style="color:#666;font-size:0.82em;margin-bottom:10px;">
    NCT:&nbsp;<code>{nct_id}</code>&nbsp;|&nbsp;
    <a href="https://clinicaltrials.gov/study/{nct_id}" target="_blank" style="color:#1565C0;">
      View on ClinicalTrials.gov ↗</a>
  </div>
  <div style="font-weight:bold;color:{color};margin-bottom:8px;">
    VERDICT: {verdict} | {conf}/100
  </div>
  <p style="text-align:{text_align};margin:6px 0;"><strong>Reason:</strong> {reason}</p>
  {dq_block}{ns_block}
</div>''')

    parts.append('</div>')
    return "".join(parts)

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
# Main pipeline  (yields: status, results_html, emails, translated_html)
# ---------------------------------------------------------------------------

def run_trialmatch(pdf_file, condition, language):
    if pdf_file is None:
        yield "Please upload a PDF file.", "", "", ""
        return
    if not condition or not condition.strip():
        yield "Please enter a condition keyword (e.g. 'type 2 diabetes').", "", "", ""
        return

    condition = condition.strip()
    language  = language or "English"

    if isinstance(pdf_file, str):
        pdf_path = pdf_file
    elif hasattr(pdf_file, "name"):
        pdf_path = pdf_file.name
    elif isinstance(pdf_file, dict):
        pdf_path = pdf_file.get("path") or pdf_file.get("name") or ""
    else:
        pdf_path = str(pdf_file)

    if not pdf_path:
        yield "ERROR: Could not determine the uploaded file path.", "", "", ""
        return

    # ── Step 1 ───────────────────────────────────────────────────────────────
    yield (
        "Step 1/4 — Reading your medical records and running clinical reasoning...\n"
        "(first run may take 2–3 minutes while the model loads)",
        "", "", "",
    )
    try:
        profile_data = extract_patient_profile(pdf_path)
    except Exception as e:
        yield f"ERROR reading PDF: {e}", _msg_html(f"Error: {e}", "#c62828"), "", ""
        return

    if isinstance(profile_data, str):
        yield profile_data, _msg_html(profile_data, "#c62828"), "", ""
        return

    patient_profile    = profile_data["raw_extraction"]
    clinical_reasoning = profile_data["clinical_reasoning"]
    key_flags          = profile_data["key_flags"]

    # ── Step 2 ───────────────────────────────────────────────────────────────
    yield "Step 2/4 — Searching ClinicalTrials.gov for open recruiting trials...", "", "", ""

    try:
        trials = fetch_trials(condition)
    except Exception as e:
        yield f"ERROR fetching trials: {e}", _msg_html(f"Error: {e}", "#c62828"), "", ""
        return

    if not trials:
        msg = ("No recruiting trials found for this condition.\n\n"
               "• Try a broader keyword (e.g. 'diabetes')\n"
               "• Try an alternative name for the condition\n"
               "• Check your internet connection")
        yield "Search complete.", _msg_html(msg), "", ""
        return

    # ── Step 3 ───────────────────────────────────────────────────────────────
    matches = []
    total   = len(trials)

    for i, trial in enumerate(trials):
        trial_title = trial.get("title", f"Trial {i + 1}")
        short       = trial_title[:72] + ("..." if len(trial_title) > 72 else "")
        yield f"Step 3/4 — Matching trial {i + 1} of {total}:\n{short}", "", "", ""
        try:
            result = match_patient_to_trial(patient_profile, clinical_reasoning, trial)
            if result["verdict"] in ("MATCH", "PARTIAL"):
                matches.append(result)
        except Exception:
            pass

    if not matches:
        msg = (f"No qualifying trials found among {total} reviewed.\n\n"
               "• Try a broader condition keyword\n"
               "• New trials open regularly — try again in a few days\n"
               "• Consult your doctor about trials they may know of")
        yield "Analysis complete.", _msg_html(msg), "", ""
        return

    # Sort by confidence descending — applies to all subsequent outputs
    matches = sorted(matches, key=lambda m: m.get("confidence_score", 0), reverse=True)
    results_html_str = _format_results_html(matches, total, key_flags)

    # ── Step 4a: Email drafts ─────────────────────────────────────────────────
    match_only = [m for m in matches if m["verdict"] == "MATCH"]
    if match_only:
        yield "Step 4/4 — Drafting inquiry emails for MATCH verdicts...", results_html_str, "", ""
        email_parts = []
        for m in match_only:
            print(f"[app] Drafting email for: {m['trial_title'][:50]}...")
            try:
                email_text = generate_inquiry_email(patient_profile, m)
                email_parts.append(
                    f"{'─' * 64}\nTrial: {m['trial_title']}\nNCT:   {m['nct_id']}\n\n{email_text}"
                )
            except Exception as e:
                email_parts.append(f"Could not draft email for {m['trial_title']}: {e}")
        emails_text = "\n\n".join(email_parts)
    else:
        emails_text = ("No full MATCH verdicts — only PARTIAL matches found.\n"
                       "Emails are drafted for MATCH verdicts only.\n"
                       "For PARTIAL matches, consult your doctor first.")

    # ── Step 4b: Translation ──────────────────────────────────────────────────
    translated_html = ""
    if language != "English":
        yield f"Step 4/4 — Translating results to {language}...", results_html_str, emails_text, ""
        try:
            t_matches       = translate_matches(matches, language)
            translated_html = _format_translated_html(t_matches, total, language, key_flags)
        except Exception as e:
            translated_html = _msg_html(f"Translation error: {e}", "#c62828")

    yield "Analysis complete.", results_html_str, emails_text, translated_html

# ---------------------------------------------------------------------------
# Gradio UI
# ---------------------------------------------------------------------------

with gr.Blocks(title="TrialMatch") as demo:

    gr.Markdown("# TrialMatch")
    gr.Markdown("### Find clinical trials you qualify for — privately, on your own computer")
    gr.HTML(_INFO_HTML)

    with gr.Tabs():

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
                    language_dropdown = gr.Dropdown(
                        choices=_LANGUAGES,
                        value="English",
                        label="Step 3 — Results Language",
                        info="Urdu and Arabic results are displayed right-to-left.",
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
                    results_html = gr.HTML(value=(
                        "<p style='color:#888;font-family:sans-serif;padding:8px;'>"
                        "Results will appear here after the analysis completes.</p>"
                    ))

                    with gr.Accordion("📧  Draft Inquiry Emails  (MATCH verdicts only)", open=False):
                        email_box = gr.Textbox(
                            label="Email Drafts",
                            interactive=False,
                            lines=18,
                            placeholder="Email drafts appear here after analysis.",
                        )
                        copy_btn = gr.Button("📋  Copy Email to Clipboard", variant="secondary")

                    with gr.Accordion("🌐  Translated Results (Urdu / Arabic / French)", open=False):
                        gr.Markdown(
                            "Select a non-English language above before running the analysis. "
                            "Urdu and Arabic are displayed right-to-left."
                        )
                        translated_output = gr.HTML(value="")

            run_btn.click(
                fn=run_trialmatch,
                inputs=[pdf_input, condition_input, language_dropdown],
                outputs=[status_box, results_html, email_box, translated_output],
            )

            copy_btn.click(
                fn=None,
                inputs=[email_box],
                outputs=[],
                js=(
                    "(text) => {"
                    "  if (!text) { alert('No email to copy yet — run the analysis first.'); return []; }"
                    "  navigator.clipboard.writeText(text)"
                    "    .then(() => alert('Email copied to clipboard!'))"
                    "    .catch(() => {"
                    "      const el = document.createElement('textarea');"
                    "      el.value = text; document.body.appendChild(el);"
                    "      el.select(); document.execCommand('copy');"
                    "      document.body.removeChild(el);"
                    "      alert('Email copied to clipboard!');"
                    "    });"
                    "  return [];"
                    "}"
                ),
            )

        with gr.Tab("System Check"):
            gr.Markdown(
                "Click **Check System** to verify that Ollama is running "
                "and that the `gemma3:4b` model is installed."
            )
            check_btn    = gr.Button("Check System", variant="secondary")
            check_output = gr.Textbox(label="System Status", interactive=False, lines=8)
            check_btn.click(fn=check_system, inputs=[], outputs=[check_output])

    gr.HTML(_DISCLAIMER_HTML)


if __name__ == "__main__":
    import socket

    def _find_free_port(start=7860, end=7880):
        for port in range(start, end + 1):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(("127.0.0.1", port)) != 0:
                    return port
        return start

    port = _find_free_port()
    print(f"Starting TrialMatch — open http://127.0.0.1:{port} in your browser")
    demo.launch(
        server_name="127.0.0.1",
        server_port=port,
        share=False,
        inbrowser=False,
        theme=gr.themes.Soft(),
    )
