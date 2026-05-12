import requests
import gradio as gr

from profile_extractor import extract_patient_profile
from trial_fetcher import fetch_trials
from matcher import match_patient_to_trial
from extras import generate_inquiry_email, translate_matches

_LANGUAGES  = ["English", "Urdu", "Arabic", "French"]
_RTL_LANGS  = {"Urdu", "Arabic"}

# ─────────────────────────────────────────────────────────────────────────────
# CSS — injected into <head> via demo.launch(css=...)
# Uses CSS custom-properties so every element responds to dark-mode toggle.
# ─────────────────────────────────────────────────────────────────────────────

_CSS = """
/* ── Design Tokens (light) ─────────────────────────────────────────────── */
:root {
    --bg:           #f1f5f9;
    --surface:      #ffffff;
    --surface-2:    #f8fafc;
    --border:       #e2e8f0;
    --border-2:     #cbd5e1;
    --text:         #0f172a;
    --text-2:       #475569;
    --text-3:       #94a3b8;
    --accent:       #2563eb;
    --accent-2:     #1d4ed8;
    --accent-bg:    #eff6ff;
    --accent-glow:  rgba(37,99,235,0.18);
    --shadow:       0 1px 3px rgba(0,0,0,0.05),0 0 0 1px rgba(0,0,0,0.03);
    --shadow-md:    0 4px 16px rgba(0,0,0,0.08),0 0 0 1px rgba(0,0,0,0.04);
    --shadow-lg:    0 12px 32px rgba(0,0,0,0.1);
    --radius:       14px;
    --radius-sm:    8px;
    --green:        #059669;  --green-2:#34d399;
    --green-bg:     #f0fdf4;  --green-bd:#6ee7b7;
    --amber:        #d97706;  --amber-2:#fbbf24;
    --amber-bg:     #fffbeb;  --amber-bd:#fde68a;
    --red:          #dc2626;  --red-2:#f87171;
    --red-bg:       #fef2f2;  --red-bd:#fecaca;
    --info:         #0ea5e9;  --info-bg:#f0f9ff;  --info-bd:#bae6fd;
}

/* ── Design Tokens (dark) ───────────────────────────────────────────────── */
html.tm-dark {
    --bg:           #070c18;
    --surface:      #0d1528;
    --surface-2:    #111e33;
    --border:       rgba(255,255,255,0.06);
    --border-2:     rgba(255,255,255,0.12);
    --text:         #e2e8f0;
    --text-2:       #94a3b8;
    --text-3:       #475569;
    --accent:       #60a5fa;
    --accent-2:     #3b82f6;
    --accent-bg:    rgba(96,165,250,0.08);
    --accent-glow:  rgba(96,165,250,0.22);
    --shadow:       0 1px 4px rgba(0,0,0,0.5),0 0 0 1px rgba(255,255,255,0.04);
    --shadow-md:    0 4px 20px rgba(0,0,0,0.55),0 0 0 1px rgba(255,255,255,0.05);
    --shadow-lg:    0 12px 40px rgba(0,0,0,0.7);
    --green:        #34d399;  --green-2:#6ee7b7;
    --green-bg:     rgba(52,211,153,0.09);  --green-bd:rgba(52,211,153,0.22);
    --amber:        #fbbf24;  --amber-2:#fde68a;
    --amber-bg:     rgba(251,191,36,0.09);  --amber-bd:rgba(251,191,36,0.22);
    --red:          #f87171;  --red-2:#fca5a5;
    --red-bg:       rgba(248,113,113,0.09); --red-bd:rgba(248,113,113,0.22);
    --info:         #38bdf8;  --info-bg:rgba(56,189,248,0.08); --info-bd:rgba(56,189,248,0.2);
}

/* ── Global ─────────────────────────────────────────────────────────────── */
html, body, .gradio-container {
    background: var(--bg) !important;
    transition: background 0.3s ease !important;
}
footer, .built-with, #footer { display: none !important; }
* { box-sizing: border-box; }
*, *::before, *::after {
    transition: background-color 0.25s ease, border-color 0.25s ease, color 0.25s ease,
                box-shadow 0.25s ease;
}
.conf-fill { transition: none !important; }

/* ── Tabs ───────────────────────────────────────────────────────────────── */
.tab-nav {
    background: var(--surface) !important;
    border-bottom: 1px solid var(--border) !important;
    border-radius: 12px 12px 0 0 !important;
    padding: 0 8px !important;
    box-shadow: var(--shadow) !important;
}
.tab-nav button {
    font-weight: 600 !important; font-size: 0.8rem !important;
    color: var(--text-2) !important; text-transform: uppercase !important;
    letter-spacing: 0.08em !important; border: none !important;
    border-bottom: 2px solid transparent !important; background: transparent !important;
    border-radius: 0 !important; margin-bottom: -1px !important;
    padding: 14px 22px !important;
}
.tab-nav button.selected { color: var(--accent) !important; border-bottom-color: var(--accent) !important; }
.tab-nav button:hover:not(.selected) { color: var(--text) !important; background: var(--surface-2) !important; }
.tabitem {
    background: var(--surface) !important; border-radius: 0 0 14px 14px !important;
    border: none !important; padding: 28px !important; box-shadow: var(--shadow) !important;
}

/* ── Buttons ────────────────────────────────────────────────────────────── */
button.primary {
    background: linear-gradient(135deg, var(--accent) 0%, var(--accent-2) 100%) !important;
    color: #fff !important; font-weight: 700 !important; font-size: 0.85rem !important;
    letter-spacing: 0.1em !important; text-transform: uppercase !important;
    border: none !important; border-radius: 10px !important; padding: 14px 24px !important;
    box-shadow: 0 4px 16px var(--accent-glow) !important;
    transition: transform 0.2s, box-shadow 0.2s !important;
}
button.primary:hover { transform: translateY(-2px) !important; box-shadow: 0 8px 24px var(--accent-glow) !important; }
button.primary:active { transform: none !important; }

button.secondary {
    background: var(--surface) !important; color: var(--text-2) !important;
    font-weight: 600 !important; font-size: 0.83rem !important;
    border: 1.5px solid var(--border-2) !important; border-radius: 8px !important;
}
button.secondary:hover { border-color: var(--accent) !important; color: var(--accent) !important; background: var(--accent-bg) !important; }

/* ── Inputs ─────────────────────────────────────────────────────────────── */
input[type=text], textarea, select {
    background: var(--surface-2) !important; color: var(--text) !important;
    border: 1.5px solid var(--border) !important; border-radius: 8px !important;
    font-size: 0.88rem !important;
}
input[type=text]::placeholder, textarea::placeholder { color: var(--text-3) !important; }
input[type=text]:focus, textarea:focus, select:focus {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 3px var(--accent-glow) !important; outline: none !important;
}
label span {
    color: var(--text-2) !important; font-weight: 700 !important;
    font-size: 0.72rem !important; text-transform: uppercase !important;
    letter-spacing: 0.1em !important;
}

/* ── Accordion ──────────────────────────────────────────────────────────── */
.accordion { background: var(--surface) !important; border: 1.5px solid var(--border) !important; border-radius: 10px !important; overflow: hidden !important; }
.accordion-header button { background: var(--surface-2) !important; color: var(--text-2) !important; font-weight: 600 !important; font-size: 0.84rem !important; }

/* ── Confidence bar animation ───────────────────────────────────────────── */
@keyframes confGrow { from { width:0%; opacity:0.3; } to { width:var(--pct); opacity:1; } }
.conf-fill { animation: confGrow 1s cubic-bezier(0.16,1,0.3,1) 0.15s forwards; }

/* ── Toast notification ─────────────────────────────────────────────────── */
@keyframes tmSlideIn  { from { transform:translateX(120%); opacity:0; } to { transform:translateX(0); opacity:1; } }
@keyframes tmSlideOut { from { transform:translateX(0);    opacity:1; } to { transform:translateX(120%); opacity:0; } }
#tm-toast {
    position:fixed; top:24px; right:24px; z-index:9999;
    padding:14px 20px; border-radius:14px;
    box-shadow:0 8px 32px rgba(0,0,0,0.28), 0 0 0 1px rgba(255,255,255,0.08);
    font-family:system-ui,sans-serif; font-size:0.88rem; font-weight:600;
    max-width:320px; display:flex; align-items:center; gap:13px;
    animation: tmSlideIn 0.45s cubic-bezier(0.16,1,0.3,1) forwards;
    cursor:pointer;
}

/* ── Status pulse ───────────────────────────────────────────────────────── */
@keyframes pulse {
    0%,100% { opacity:1; transform:scale(1); }
    50%      { opacity:0.25; transform:scale(0.72); }
}

/* ── Responsive ─────────────────────────────────────────────────────────── */
@media (max-width: 900px) {
    .gap, [class*="row"] { flex-wrap: wrap !important; }
    [class*="column"] { min-width: 100% !important; width: 100% !important; flex: 1 1 100% !important; }
    .tabitem { padding: 16px !important; }
}

/* ── Scrollbar ──────────────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border-2); border-radius: 2px; }

"""

# ─────────────────────────────────────────────────────────────────────────────
# JavaScript — runs via demo.load(js=...) after page hydration.
# Uses MutationObserver to wire the #tm-toggle button that lives inside
# gr.HTML (which renders async). No onclick attribute needed — addEventListener
# is added programmatically so Gradio's HTML sanitiser can't block it.
# ─────────────────────────────────────────────────────────────────────────────

_THEME_JS = """
() => {
    // ── Theme ──────────────────────────────────────────────────────────────
    const saved  = localStorage.getItem('tm-theme');
    const osDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const isDark = saved === 'dark' || (!saved && osDark);
    document.documentElement.classList.toggle('tm-dark', isDark);

    let wired = false;
    const wire = () => {
        const btn = document.getElementById('tm-toggle');
        if (!btn || wired) return;
        wired = true;
        btn.textContent = document.documentElement.classList.contains('tm-dark')
            ? '☀  Light' : '☾  Dark';
        btn.addEventListener('click', function() {
            const dark = document.documentElement.classList.toggle('tm-dark');
            localStorage.setItem('tm-theme', dark ? 'dark' : 'light');
            this.textContent = dark ? '☀  Light' : '☾  Dark';
        });
    };
    wire();
    new MutationObserver(wire).observe(document.body, { childList: true, subtree: true });

    // ── Notifications (in-app toast + optional desktop) ────────────────────
    if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission();
    }

    const showToast = (emoji, heading, body, isError) => {
        const old = document.getElementById('tm-toast');
        if (old) old.remove();

        const bg     = isError ? '#b91c1c'  : '#065f46';
        const border = isError ? '#fca5a5'  : '#6ee7b7';

        const t = document.createElement('div');
        t.id = 'tm-toast';
        t.style.background = bg;
        t.style.border     = '1.5px solid ' + border;
        t.innerHTML =
            '<span style="font-size:1.6rem;flex-shrink:0;line-height:1;">' + emoji + '</span>' +
            '<div>' +
              '<div style="color:#fff;font-weight:700;margin-bottom:3px;">' + heading + '</div>' +
              '<div style="color:rgba(255,255,255,0.85);font-size:0.8rem;font-weight:400;line-height:1.45;">' + body + '</div>' +
            '</div>' +
            '<span style="margin-left:auto;color:rgba(255,255,255,0.5);font-size:1.1rem;flex-shrink:0;padding-left:8px;">✕</span>';

        t.addEventListener('click', () => {
            t.style.animation = 'tmSlideOut 0.3s ease forwards';
            setTimeout(() => t.remove(), 300);
        });
        document.body.appendChild(t);

        setTimeout(() => {
            if (!document.getElementById('tm-toast')) return;
            t.style.animation = 'tmSlideOut 0.3s ease forwards';
            setTimeout(() => t.remove(), 300);
        }, 8000);

        if ('Notification' in window && Notification.permission === 'granted') {
            new Notification(heading, { body });
        }
    };

    let notifyWired = false;
    const wireNotify = () => {
        const el = document.getElementById('tm-status');
        if (!el || notifyWired) return;
        notifyWired = true;
        new MutationObserver(() => {
            const txt = el.innerText || '';
            if (txt.includes('Step 1/4')) {
                delete el.dataset.notified;
            } else if (txt.includes('Analysis complete') && !el.dataset.notified) {
                el.dataset.notified = '1';
                showToast('✅', 'TrialMatch — Done!', 'Your trial matching is complete. Results are ready below.', false);
            } else if (txt.includes('ERROR:') && !el.dataset.notified) {
                el.dataset.notified = '1';
                showToast('❌', 'TrialMatch — Error', 'An error occurred. Check the status box for details.', true);
            }
        }).observe(el, { childList: true, subtree: true, characterData: true });
    };
    wireNotify();
    new MutationObserver(wireNotify).observe(document.body, { childList: true, subtree: true });

    return [];
}
"""

# ─────────────────────────────────────────────────────────────────────────────
# Static HTML blocks  (all use CSS variables → dark-mode aware)
# ─────────────────────────────────────────────────────────────────────────────

_HEADER_HTML = """
<div style="position:relative;background:linear-gradient(135deg,#060f24 0%,#0f2151 55%,#1d4ed8 100%);
            padding:30px 36px;border-radius:16px;margin-bottom:20px;
            box-shadow:0 20px 48px rgba(6,15,36,0.45);">

  <!-- Theme toggle — wired via addEventListener in _THEME_JS, no onclick needed -->
  <button id="tm-toggle"
    style="position:absolute;top:18px;right:18px;cursor:pointer;
           background:rgba(255,255,255,0.1);color:rgba(255,255,255,0.9);
           border:1px solid rgba(255,255,255,0.22);border-radius:20px;
           padding:6px 14px;font-size:0.78rem;font-weight:600;
           font-family:system-ui,sans-serif;letter-spacing:0.04em;
           transition:background 0.2s,border-color 0.2s;">
    ☾  Dark
  </button>

  <!-- Brand -->
  <div style="display:flex;align-items:center;gap:18px;margin-bottom:16px;">
    <div style="background:rgba(255,255,255,0.12);border:1px solid rgba(255,255,255,0.18);
                border-radius:14px;padding:13px;font-size:1.9rem;line-height:1;
                box-shadow:0 4px 16px rgba(0,0,0,0.3);">🧬</div>
    <div>
      <div style="color:white;font-size:2rem;font-weight:800;letter-spacing:-0.04em;
                  font-family:system-ui,sans-serif;line-height:1;">TrialMatch</div>
      <div style="color:rgba(255,255,255,0.65);font-size:0.9rem;margin-top:5px;
                  font-family:system-ui,sans-serif;">
        AI-powered clinical trial matching — private, local, instant
      </div>
    </div>
  </div>

  <!-- Feature pills -->
  <div style="display:flex;gap:7px;flex-wrap:wrap;">
    <span style="background:rgba(255,255,255,0.1);color:rgba(255,255,255,0.88);
                 padding:5px 12px;border-radius:20px;font-size:0.75rem;font-weight:600;
                 border:1px solid rgba(255,255,255,0.18);font-family:system-ui,sans-serif;
                 letter-spacing:0.02em;">🔒 100% Private</span>
    <span style="background:rgba(255,255,255,0.1);color:rgba(255,255,255,0.88);
                 padding:5px 12px;border-radius:20px;font-size:0.75rem;font-weight:600;
                 border:1px solid rgba(255,255,255,0.18);font-family:system-ui,sans-serif;
                 letter-spacing:0.02em;">💻 Runs Locally</span>
    <span style="background:rgba(255,255,255,0.1);color:rgba(255,255,255,0.88);
                 padding:5px 12px;border-radius:20px;font-size:0.75rem;font-weight:600;
                 border:1px solid rgba(255,255,255,0.18);font-family:system-ui,sans-serif;
                 letter-spacing:0.02em;">🤖 Gemma 4</span>
    <span style="background:rgba(255,255,255,0.1);color:rgba(255,255,255,0.88);
                 padding:5px 12px;border-radius:20px;font-size:0.75rem;font-weight:600;
                 border:1px solid rgba(255,255,255,0.18);font-family:system-ui,sans-serif;
                 letter-spacing:0.02em;">🏥 ClinicalTrials.gov</span>
  </div>
</div>
"""

_INFO_HTML = """
<div style="background:var(--red-bg);border:1px solid var(--red-bd);border-left:4px solid var(--red);
            padding:13px 18px;border-radius:10px;margin:0 0 20px;
            display:flex;align-items:flex-start;gap:12px;font-family:system-ui,sans-serif;">
  <span style="font-size:1.25rem;flex-shrink:0;line-height:1.4;">⚕️</span>
  <div>
    <strong style="color:var(--red);display:block;margin-bottom:3px;font-size:0.88rem;">
      Medical Disclaimer
    </strong>
    <span style="color:var(--text-2);font-size:0.83rem;line-height:1.55;">
      For information only — always consult your doctor.
      Records are processed entirely on your device.
      The only external call is a condition keyword sent to ClinicalTrials.gov.
    </span>
  </div>
</div>
"""

_DISCLAIMER_HTML = """
<div style="text-align:center;padding:22px 0 10px;color:var(--text-3);
            font-size:0.76rem;font-family:system-ui,sans-serif;line-height:1.7;">
  TrialMatch does not provide medical advice, diagnosis, or treatment.
  It is a research aid only. Always seek guidance from a licensed healthcare professional.<br>
  Built for the <em>Google DeepMind Gemma 4 Good Hackathon</em>.
</div>
"""

# ─────────────────────────────────────────────────────────────────────────────
# HTML helpers
# ─────────────────────────────────────────────────────────────────────────────

def _msg_html(text, level="info"):
    safe  = text.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
    paras = "".join(f"<p style='margin:5px 0;'>{l}</p>" for l in safe.split("\n") if l.strip())
    c = {"info":"var(--text-2)","error":"var(--red)","ok":"var(--green)"}.get(level,"var(--text-2)")
    return (
        f'<div style="font-family:system-ui,sans-serif;padding:16px 18px;'
        f'background:var(--surface-2);border:1.5px solid var(--border);'
        f'border-radius:10px;color:{c};">{paras}</div>'
    )


def _status_html(text, done=False, warn=False):
    if not text:
        return ""
    no_spinner = done or warn
    if done:
        border, bg, icon, dot_color = "var(--green-bd)", "var(--green-bg)", "✓", "var(--green)"
    elif warn:
        border, bg, icon, dot_color = "var(--amber-bd)", "var(--amber-bg)", "⚠", "var(--amber)"
    else:
        border, bg, icon, dot_color = "var(--border)", "var(--surface-2)", "▶", "var(--accent)"

    lines = [l.strip() for l in text.split("\n") if l.strip()]
    rows  = []
    for line in lines:
        if any(line.startswith(p) for p in ("Step", "Analysis")):
            rows.append(
                f'<div style="display:flex;gap:10px;align-items:flex-start;margin:6px 0;">'
                f'<span style="color:{dot_color};font-weight:800;font-size:0.8rem;'
                f'padding-top:1px;flex-shrink:0;">{icon}</span>'
                f'<span style="color:var(--text);font-size:0.88rem;font-weight:500;">'
                f'{line}</span></div>'
            )
        elif line.startswith("("):
            rows.append(
                f'<div style="color:var(--text-3);font-size:0.79rem;'
                f'margin:2px 0 2px 22px;font-style:italic;">{line}</div>'
            )
        else:
            rows.append(
                f'<div style="color:var(--text-2);font-size:0.87rem;margin:4px 0;">'
                f'{line}</div>'
            )

    spinner = "" if no_spinner else (
        f'<div style="margin-top:12px;display:flex;align-items:center;gap:8px;">'
        f'<span style="display:inline-block;width:7px;height:7px;background:var(--accent);'
        f'border-radius:50%;animation:pulse 1.2s ease-in-out infinite;"></span>'
        f'<span style="color:var(--text-3);font-size:0.79rem;font-style:italic;">Processing…</span>'
        f'</div>'
    )

    return (
        f'<div style="font-family:system-ui,sans-serif;background:{bg};'
        f'border:1.5px solid {border};border-radius:10px;padding:16px 18px;">'
        f'{"".join(rows)}{spinner}</div>'
    )


def _confidence_bar_html(confidence, bar_color, bar_light):
    return (
        f'<div style="margin:16px 0 12px;">'
        f'<div style="display:flex;justify-content:space-between;'
        f'align-items:center;margin-bottom:7px;">'
        f'<span style="font-size:0.69rem;font-weight:700;color:var(--text-3);'
        f'text-transform:uppercase;letter-spacing:0.1em;">Match Confidence</span>'
        f'<span style="font-size:0.92rem;font-weight:800;color:{bar_color};">'
        f'{confidence}%</span></div>'
        f'<div style="background:var(--surface-2);border-radius:8px;'
        f'height:8px;overflow:hidden;border:1px solid var(--border);">'
        f'<div class="conf-fill" style="--pct:{confidence}%;height:100%;'
        f'background:linear-gradient(90deg,{bar_light},{bar_color});'
        f'border-radius:8px;"></div></div></div>'
    )


def _build_criterion_rows(match):
    verdict = match.get("verdict", "UNKNOWN")
    detail  = match.get("disqualifier_detail", "")
    dq_line = match.get("disqualifiers", "NONE")
    failed, borderline = [], []

    if detail:
        section = None
        for line in detail.split("\n"):
            s = line.strip()
            if not s:
                continue
            up = s.upper()
            if "FAILED CRITERIA:" in up:
                section = "failed"
            elif "BORDERLINE CRITERIA:" in up:
                section = "borderline"
            elif section and up not in ("NONE", ""):
                text = s.lstrip("0123456789.-) ").strip("\"'")
                if "— REASON:" in text:
                    text = text.split("— REASON:")[0].strip().strip("\"'")
                if text and len(text) > 3 and "NONE" not in text.upper():
                    snip = text[:72] + ("…" if len(text) > 72 else "")
                    (failed if section == "failed" else borderline).append(snip)

    if verdict == "MATCH":
        return [
            ("All eligibility criteria reviewed", "✓  Met",            "var(--green)", "var(--green-bg)"),
            ("Exclusion criteria",                "✓  None triggered", "var(--green)", "var(--green-bg)"),
        ]

    rows = (
        [(i, "✗  Failed",     "var(--red)",   "var(--red-bg)")   for i in failed] +
        [(i, "⚠  Borderline", "var(--amber)", "var(--amber-bg)") for i in borderline]
    )

    if not rows:
        dq   = (dq_line[:72] if dq_line and dq_line.upper() not in ("NONE","")
                else "Requirements uncertain — manual review needed")
        rows = [(dq,
                 "⚠  Borderline" if verdict == "PARTIAL" else "✗  Failed",
                 "var(--amber)"   if verdict == "PARTIAL" else "var(--red)",
                 "var(--amber-bg)" if verdict == "PARTIAL" else "var(--red-bg)")]
    return rows


def _format_results_html(matches, total_trials, key_flags=None):
    sorted_m = sorted(matches, key=lambda m: m.get("confidence_score", 0), reverse=True)
    parts = ['<div style="font-family:system-ui,sans-serif;">']

    # Clinical flags banner
    if key_flags:
        items = "".join(
            f'<li style="margin:4px 0;color:var(--text-2);font-size:0.875rem;">{f}</li>'
            for f in key_flags
        )
        parts.append(
            '<div style="background:var(--green-bg);border:1px solid var(--green-bd);'
            'border-left:4px solid var(--green);padding:14px 18px;border-radius:10px;'
            'margin-bottom:18px;">'
            '<strong style="color:var(--green);font-size:0.85rem;">🩺 Clinical Profile Summary</strong>'
            f'<ul style="margin:10px 0 0 18px;padding:0;">{items}</ul></div>'
        )

    parts.append(
        f'<p style="color:var(--text-3);margin-bottom:16px;font-size:0.83rem;'
        f'letter-spacing:0.01em;">'
        f'<strong style="color:var(--text);">{len(sorted_m)}</strong> potential match(es) '
        f'from <strong style="color:var(--text);">{total_trials}</strong> trial(s) reviewed '
        f'— sorted by confidence.</p>'
    )

    for m in sorted_m:
        verdict = m["verdict"]
        conf    = m["confidence_score"]

        if conf >= 80:
            bar_color, bar_light = "var(--green)",  "var(--green-2)"
            banner_bg             = "var(--green-bg)"
        elif conf >= 50:
            bar_color, bar_light = "var(--amber)",  "var(--amber-2)"
            banner_bg             = "var(--amber-bg)"
        else:
            bar_color, bar_light = "var(--red)",    "var(--red-2)"
            banner_bg             = "var(--red-bg)"

        verdict_icon  = "✅" if verdict == "MATCH" else "⚠️" if verdict == "PARTIAL" else "❌"
        verdict_label = f"{verdict_icon} {verdict}"

        # Phase / sponsor / completion date chips
        phase           = m.get("phase",           "")
        sponsor         = m.get("sponsor",         "")
        completion_date = m.get("completion_date", "")
        chips = ""
        if phase and phase != "Not specified":
            chips += (
                f'<span style="background:var(--accent-bg);color:var(--accent);'
                f'padding:2px 9px;border-radius:20px;font-size:0.73rem;font-weight:600;">'
                f'{phase}</span> '
            )
        if sponsor and sponsor not in ("Unknown sponsor",):
            sp = sponsor[:30] + ("…" if len(sponsor) > 30 else "")
            chips += (
                f'<span style="background:var(--surface-2);color:var(--text-2);'
                f'padding:2px 9px;border-radius:20px;font-size:0.73rem;font-weight:600;">'
                f'{sp}</span> '
            )
        if completion_date:
            chips += (
                f'<span style="background:var(--surface-2);color:var(--text-3);'
                f'padding:2px 9px;border-radius:20px;font-size:0.73rem;font-weight:600;">'
                f'📅 {completion_date}</span> '
            )

        # Criterion table
        crit_rows = _build_criterion_rows(m)
        tbody = "".join(
            f'<tr style="background:{rb};">'
            f'<td style="padding:7px 12px;border:1px solid var(--border);'
            f'font-size:0.8em;color:var(--text-2);">{cr}</td>'
            f'<td style="padding:7px 12px;border:1px solid var(--border);text-align:center;'
            f'color:{tc};font-weight:700;white-space:nowrap;font-size:0.8em;">{st}</td>'
            f'</tr>'
            for cr, st, tc, rb in crit_rows
        )
        table_html = (
            '<div style="margin:14px 0;border-radius:8px;overflow:hidden;'
            'border:1px solid var(--border);">'
            '<div style="background:var(--surface-2);padding:7px 12px;'
            'border-bottom:1px solid var(--border);">'
            '<span style="font-size:0.69rem;font-weight:700;color:var(--text-3);'
            'text-transform:uppercase;letter-spacing:0.1em;">Eligibility Assessment</span></div>'
            f'<table style="width:100%;border-collapse:collapse;"><tbody>{tbody}</tbody></table>'
            '</div>'
        )

        # Contact
        cn, ce, cp = (m.get("contact_name",""), m.get("contact_email",""), m.get("contact_phone",""))
        contact_parts = []
        if cn:
            contact_parts.append(f'<strong style="color:var(--text);">{cn}</strong>')
        if ce and ce not in ("","see ClinicalTrials.gov"):
            contact_parts.append(
                f'<a href="mailto:{ce}" style="color:var(--accent);text-decoration:none;">{ce}</a>'
            )
        if cp and cp not in ("","see ClinicalTrials.gov"):
            contact_parts.append(f'<span style="color:var(--text-2);">{cp}</span>')
        contact_html = (
            f'<div style="margin-top:12px;padding-top:12px;border-top:1px solid var(--border);'
            f'display:flex;align-items:center;gap:6px;flex-wrap:wrap;font-size:0.82rem;">'
            f'<span style="color:var(--text-3);">📞</span>'
            + " &nbsp;·&nbsp; ".join(contact_parts) + '</div>'
        ) if contact_parts else ""

        nct_id    = m["nct_id"]
        reason    = m.get("reason", "")
        next_step = m.get("next_step", "")
        reason_html = (
            f'<p style="margin:0 0 12px;font-size:0.875rem;color:var(--text-2);line-height:1.65;">'
            f'<strong style="color:var(--text);">Reason: </strong>{reason}</p>'
        ) if reason else ""
        ns_html = (
            f'<div style="background:var(--info-bg);border:1px solid var(--info-bd);'
            f'border-left:3px solid var(--info);padding:10px 14px;border-radius:8px;'
            f'margin:12px 0;font-size:0.84rem;color:var(--info);">'
            f'<strong>Next Step:</strong> {next_step}</div>'
        ) if next_step else ""

        parts.append(f"""
<div style="background:var(--surface);border-radius:var(--radius);margin:14px 0;
            box-shadow:var(--shadow-md);overflow:hidden;position:relative;">
  <div style="height:4px;background:linear-gradient(90deg,{bar_light},{bar_color});"></div>
  <div style="padding:22px 26px;">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;
                gap:14px;margin-bottom:12px;">
      <div style="flex:1;min-width:0;">
        <div style="font-weight:700;font-size:1rem;color:var(--text);
                    line-height:1.45;margin-bottom:9px;">
          {m["trial_title"]}
        </div>
        <div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center;">
          <code style="background:var(--surface-2);color:var(--text-2);padding:2px 8px;
                       border-radius:5px;font-size:0.75rem;border:1px solid var(--border);">
            {nct_id}
          </code>
          {chips}
          <a href="https://clinicaltrials.gov/study/{nct_id}" target="_blank"
             style="color:var(--accent);font-size:0.78rem;font-weight:600;
                    text-decoration:none;">View on ClinicalTrials.gov ↗</a>
        </div>
      </div>
      <div style="background:{banner_bg};color:{bar_color};padding:7px 16px;
                  border-radius:20px;font-weight:700;font-size:0.78rem;
                  white-space:nowrap;flex-shrink:0;border:1.5px solid {bar_color};">
        {verdict_label}
      </div>
    </div>
    {_confidence_bar_html(conf, bar_color, bar_light)}
    <div style="border-top:1px solid var(--border);margin:14px 0;"></div>
    {reason_html}{table_html}{ns_html}{contact_html}
  </div>
</div>""")

    parts.append('</div>')
    return "".join(parts)


def _format_translated_html(matches, total_trials, language, key_flags=None):
    is_rtl     = language in _RTL_LANGS
    dir_attr   = 'dir="rtl"' if is_rtl else ''
    text_align = "right" if is_rtl else "left"

    parts = [
        f'<div style="font-family:system-ui,sans-serif;" {dir_attr}>',
        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:16px;">'
        f'<span style="font-size:1.3rem;">🌐</span>'
        f'<span style="color:var(--accent);font-weight:700;font-size:0.95rem;">'
        f'Translated Results — {language}</span></div>',
    ]
    if key_flags:
        items = "".join(
            f'<li style="margin:4px 0;font-size:0.875rem;color:var(--text-2);">{f}</li>'
            for f in key_flags
        )
        parts.append(
            f'<div style="background:var(--accent-bg);border:1px solid var(--border-2);'
            f'padding:12px 16px;border-radius:8px;margin-bottom:14px;">'
            f'<ul style="margin:0;padding-left:18px;">{items}</ul></div>'
        )
    parts.append(
        f'<p style="color:var(--text-3);margin-bottom:12px;font-size:0.83rem;">'
        f'Found {len(matches)} of {total_trials} reviewed.</p>'
    )

    for m in matches:
        verdict = m["verdict"]
        conf    = m["confidence_score"]
        color   = ("var(--green)" if verdict == "MATCH"
                   else "var(--amber)" if verdict == "PARTIAL" else "var(--red)")
        nct_id  = m.get("nct_id", "")
        reason  = m.get("reason", "")
        dq      = m.get("disqualifiers", "NONE")
        ns      = m.get("next_step", "")

        dq_block = (
            f'<p style="text-align:{text_align};margin:8px 0;font-size:0.875rem;'
            f'color:var(--text-2);"><strong>Disqualifiers:</strong> {dq}</p>'
            if dq and dq.upper() not in ("NONE", "") else ""
        )
        ns_block = (
            f'<p style="text-align:{text_align};margin:8px 0;font-size:0.875rem;'
            f'color:var(--text-2);"><strong>Next Step:</strong> {ns}</p>'
            if ns else ""
        )

        parts.append(f"""
<div style="background:var(--surface);border-radius:12px;padding:18px 22px;margin:10px 0;
            box-shadow:var(--shadow-md);border-left:4px solid {color};" {dir_attr}>
  <div style="font-weight:700;margin-bottom:6px;font-size:0.95rem;color:var(--text);">{m.get("trial_title","")}</div>
  <div style="color:var(--text-3);font-size:0.78rem;margin-bottom:10px;">
    NCT:&nbsp;<code style="background:var(--surface-2);padding:2px 6px;border-radius:4px;">{nct_id}</code>
    &nbsp;·&nbsp;
    <a href="https://clinicaltrials.gov/study/{nct_id}" target="_blank"
       style="color:var(--accent);font-weight:600;text-decoration:none;">View ↗</a>
  </div>
  <div style="display:inline-block;background:var(--surface-2);color:{color};
              padding:4px 12px;border-radius:20px;font-weight:700;font-size:0.8rem;
              margin-bottom:10px;border:1px solid var(--border);">
    {verdict} · {conf}/100
  </div>
  <p style="text-align:{text_align};margin:8px 0;font-size:0.875rem;color:var(--text-2);">
    <strong>Reason:</strong> {reason}
  </p>
  {dq_block}{ns_block}
</div>""")

    parts.append('</div>')
    return "".join(parts)

# ─────────────────────────────────────────────────────────────────────────────
# System check
# ─────────────────────────────────────────────────────────────────────────────

def _check_row(status, message):
    cfg = {
        "ok":    ("var(--green)", "var(--green-bg)", "var(--green-bd)", "✓"),
        "error": ("var(--red)",   "var(--red-bg)",   "var(--red-bd)",   "✗"),
        "warn":  ("var(--amber)", "var(--amber-bg)", "var(--amber-bd)", "!"),
    }
    color, bg, border, icon = cfg.get(status, cfg["warn"])
    return (
        f'<div style="background:{bg};border:1px solid {border};border-left:4px solid {color};'
        f'padding:14px 18px;border-radius:10px;margin:8px 0;'
        f'display:flex;align-items:center;gap:14px;font-family:system-ui,sans-serif;">'
        f'<span style="background:{color};color:white;border-radius:50%;'
        f'width:26px;height:26px;display:inline-flex;align-items:center;'
        f'justify-content:center;font-weight:700;font-size:0.85rem;flex-shrink:0;">'
        f'{icon}</span>'
        f'<span style="color:{color};font-weight:600;font-size:0.88rem;">{message}</span>'
        f'</div>'
    )


def check_system():
    from utils import MODEL
    rows = []
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        resp.raise_for_status()
        rows.append(_check_row("ok", "Ollama is running"))
        installed = [m.get("name", "") for m in resp.json().get("models", [])]
        if any(MODEL in n for n in installed):
            rows.append(_check_row("ok", f"{MODEL} is installed — ready to run!"))
        else:
            rows.append(_check_row("error", f"{MODEL} not found.  Fix:  ollama pull {MODEL}"))
            if installed:
                rows.append(
                    f'<p style="font-size:0.82rem;color:var(--text-3);margin:0 0 4px 44px;'
                    f'font-family:system-ui,sans-serif;">'
                    f'Installed: {", ".join(installed)}</p>'
                )
    except requests.exceptions.ConnectionError:
        rows.append(_check_row("error", "Ollama is NOT running.  Fix:  ollama serve"))
    except Exception as e:
        rows.append(_check_row("warn", f"Could not check Ollama: {e}"))
    return f'<div style="padding:4px;">{"".join(rows)}</div>'

# ─────────────────────────────────────────────────────────────────────────────
# Main pipeline  (generator — yields 4-tuples)
# ─────────────────────────────────────────────────────────────────────────────

def run_trialmatch(pdf_file, condition, language):
    if pdf_file is None:
        yield _status_html("⚠  Please upload a PDF file before running.", warn=True), "", "", ""
        return
    if not condition or not condition.strip():
        yield _status_html("⚠  Please enter a condition keyword (e.g. 'type 2 diabetes').", warn=True), "", "", ""
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
        yield _status_html("ERROR: Could not determine the uploaded file path."), "", "", ""
        return

    yield (
        _status_html(
            "Step 1/4 — Reading your medical records and running clinical reasoning...\n"
            "(first run may take 2–3 minutes while the model loads)"
        ),
        "", "", "",
    )
    try:
        profile_data = extract_patient_profile(pdf_path)
    except Exception as e:
        yield _status_html(f"ERROR reading PDF: {e}"), _msg_html(f"Error: {e}", "error"), "", ""
        return

    if isinstance(profile_data, str):
        yield _status_html(profile_data), _msg_html(profile_data, "error"), "", ""
        return

    patient_profile    = profile_data["raw_extraction"]
    clinical_reasoning = profile_data["clinical_reasoning"]
    key_flags          = profile_data["key_flags"]

    yield _status_html("Step 2/4 — Searching ClinicalTrials.gov for open recruiting trials..."), "", "", ""
    try:
        trials = fetch_trials(condition)
    except Exception as e:
        yield _status_html(f"ERROR fetching trials: {e}"), _msg_html(f"Error: {e}", "error"), "", ""
        return

    if not trials:
        msg = ("No recruiting trials found for this condition.\n\n"
               "• Try a broader keyword (e.g. 'diabetes')\n"
               "• Try an alternative name for the condition\n"
               "• Check your internet connection")
        yield _status_html("Search complete.", done=True), _msg_html(msg), "", ""
        return

    matches = []
    total   = len(trials)
    for i, trial in enumerate(trials):
        trial_title = trial.get("title", f"Trial {i + 1}")
        short       = trial_title[:72] + ("…" if len(trial_title) > 72 else "")
        yield _status_html(f"Step 3/4 — Matching trial {i + 1} of {total}:\n{short}"), "", "", ""
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
        yield _status_html("Analysis complete.", done=True), _msg_html(msg), "", ""
        return

    matches          = sorted(matches, key=lambda m: m.get("confidence_score", 0), reverse=True)
    results_html_str = _format_results_html(matches, total, key_flags)

    match_only = [m for m in matches if m["verdict"] == "MATCH"]
    if match_only:
        yield _status_html("Step 4/4 — Drafting inquiry emails for MATCH verdicts..."), results_html_str, "", ""
        email_parts = []
        for m in match_only:
            print(f"[app] Drafting email for: {m['trial_title'][:50]}…")
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
                       "Consult your doctor for PARTIAL matches.")

    translated_html = ""
    if language != "English":
        yield _status_html(f"Step 4/4 — Translating results to {language}…"), results_html_str, emails_text, ""
        try:
            t_matches       = translate_matches(matches, language)
            translated_html = _format_translated_html(t_matches, total, language, key_flags)
        except Exception as e:
            translated_html = _msg_html(f"Translation error: {e}", "error")

    yield _status_html("Analysis complete.", done=True), results_html_str, emails_text, translated_html

# ─────────────────────────────────────────────────────────────────────────────
# Placeholder HTML (uses CSS variables → dark-mode aware)
# ─────────────────────────────────────────────────────────────────────────────

_STATUS_PLACEHOLDER = (
    '<div style="font-family:system-ui,sans-serif;background:var(--surface-2);'
    'border:1.5px solid var(--border);border-radius:10px;padding:16px 18px;'
    'color:var(--text-3);font-size:0.86rem;">'
    'Status updates appear here once you click Run…</div>'
)

_RESULTS_PLACEHOLDER = (
    '<div style="font-family:system-ui,sans-serif;background:var(--surface-2);'
    'border:1.5px dashed var(--border-2);border-radius:12px;'
    'padding:48px 24px;text-align:center;">'
    '<div style="font-size:2.2rem;margin-bottom:14px;">🧬</div>'
    '<div style="font-weight:700;color:var(--text-2);margin-bottom:6px;font-size:0.95rem;">No results yet</div>'
    '<div style="font-size:0.83rem;color:var(--text-3);">Upload a PDF, enter a condition, and click Run.</div>'
    '</div>'
)

# ─────────────────────────────────────────────────────────────────────────────
# Gradio layout
# ─────────────────────────────────────────────────────────────────────────────

with gr.Blocks(title="TrialMatch") as demo:

    # Header contains the #tm-toggle button; _THEME_JS wires it via addEventListener
    gr.HTML(_HEADER_HTML)
    gr.HTML(_INFO_HTML)

    with gr.Tabs():

        with gr.Tab("🔬  Run Analysis"):
            with gr.Row(equal_height=False):

                # ── Left: inputs ──────────────────────────────────────────────
                with gr.Column(scale=1, min_width=280):
                    pdf_input = gr.File(
                        label="Medical Records (PDF)",
                        file_types=[".pdf"],
                        type="filepath",
                    )
                    condition_input = gr.Textbox(
                        label="Primary Condition",
                        placeholder="e.g. type 2 diabetes, lung cancer…",
                        lines=1,
                    )
                    language_dropdown = gr.Dropdown(
                        choices=_LANGUAGES,
                        value="English",
                        label="Results Language",
                        info="Urdu and Arabic render right-to-left.",
                    )
                    run_btn = gr.Button("▶  Run TrialMatch", variant="primary")
                    gr.HTML(
                        '<p style="font-size:0.76rem;color:var(--text-3);margin-top:6px;'
                        'text-align:center;font-family:system-ui,sans-serif;">'
                        'First run takes 2–3 min while the model loads</p>'
                    )

                # ── Right: outputs ─────────────────────────────────────────────
                with gr.Column(scale=2, min_width=380):
                    status_box   = gr.HTML(value=_STATUS_PLACEHOLDER, elem_id="tm-status")
                    results_html = gr.HTML(value=_RESULTS_PLACEHOLDER)

                    with gr.Accordion("📧  Draft Inquiry Emails  (MATCH verdicts only)", open=False):
                        email_box = gr.Textbox(
                            label="Email Drafts",
                            interactive=False,
                            lines=18,
                            placeholder="Email drafts appear here after analysis completes.",
                        )
                        copy_btn = gr.Button("📋  Copy to Clipboard", variant="secondary")

                    with gr.Accordion("🌐  Translated Results", open=False):
                        gr.HTML(
                            '<p style="font-size:0.82rem;color:var(--text-3);margin:0 0 10px;'
                            'font-family:system-ui,sans-serif;">'
                            'Select a non-English language above before running. '
                            'Urdu and Arabic are displayed right-to-left.</p>'
                        )
                        translated_output = gr.HTML(value="")

            run_btn.click(
                fn=run_trialmatch,
                inputs=[pdf_input, condition_input, language_dropdown],
                outputs=[status_box, results_html, email_box, translated_output],
            )
            copy_btn.click(
                fn=None, inputs=[email_box], outputs=[],
                js=(
                    "(text) => {"
                    "  if (!text){alert('No email yet — run the analysis first.');return[];}"
                    "  navigator.clipboard.writeText(text)"
                    "    .then(()=>alert('Copied to clipboard!'))"
                    "    .catch(()=>{"
                    "      const el=document.createElement('textarea');"
                    "      el.value=text;document.body.appendChild(el);"
                    "      el.select();document.execCommand('copy');"
                    "      document.body.removeChild(el);"
                    "      alert('Copied to clipboard!');"
                    "    });"
                    "  return [];"
                    "}"
                ),
            )

        with gr.Tab("⚙️  System Check"):
            gr.HTML(
                '<p style="font-family:system-ui,sans-serif;color:var(--text-2);'
                'font-size:0.88rem;margin-bottom:14px;">'
                'Verify that Ollama is running and '
                '<code style="background:var(--surface-2);padding:2px 6px;border-radius:4px;">'
                'gemma4:e4b</code> is installed before running the analysis.</p>'
            )
            check_btn    = gr.Button("Check System", variant="secondary")
            check_output = gr.HTML(
                value='<div style="color:var(--text-3);font-family:system-ui,sans-serif;'
                      'font-size:0.86rem;padding:8px 0;">Click Check System to begin…</div>'
            )
            check_btn.click(fn=check_system, inputs=[], outputs=[check_output])

    gr.HTML(_DISCLAIMER_HTML)

    # Wire the #tm-toggle button and restore saved theme on every page load
    demo.load(fn=None, inputs=[], outputs=[], js=_THEME_JS)


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
        css=_CSS,
    )
