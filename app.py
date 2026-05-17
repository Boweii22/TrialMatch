import requests
import time
import gradio as gr

from profile_extractor import extract_patient_profile
from trial_fetcher import fetch_trials, db_exists, db_count, is_online
from matcher import match_patient_to_trial, generate_reasoning_chain
from extras import generate_inquiry_email, translate_matches

_LANGUAGES  = ["English", "Urdu", "Arabic", "Hindi", "Spanish", "French", "Swahili",
               "Chinese", "Portuguese", "Bengali"]
_RTL_LANGS  = {"Urdu", "Arabic"}

# Computed once at startup — used in the DB info line under the search box
_DB_TRIAL_COUNT = db_count()
_DB_INFO = (
    f"🔌 Local database: {_DB_TRIAL_COUNT:,} trials · 37 conditions — works fully offline"
    if _DB_TRIAL_COUNT > 0
    else "🌐 No local database yet — will search ClinicalTrials.gov online"
)

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

/* ── Light mode: force Gradio's own CSS variables so text is always visible */
/* Without this, Gradio's Soft theme can bleed white text onto white bg      */
/* on mobile browsers that respect prefers-color-scheme at the theme level.  */
html:not(.tm-dark) {
    color-scheme: light;
    --body-background-fill:            #f1f5f9 !important;
    --body-background-fill-secondary:  #ffffff !important;
    --block-background-fill:           #ffffff !important;
    --block-border-color:              #e2e8f0 !important;
    --block-label-background-fill:     #f8fafc !important;
    --block-label-text-color:          #475569 !important;
    --block-title-text-color:          #0f172a !important;
    --block-info-text-color:           #475569 !important;
    --body-text-color:                 #0f172a !important;
    --body-text-color-subdued:         #475569 !important;
    --color-accent:                    #2563eb !important;
    --color-accent-soft:               #eff6ff !important;
    --input-background-fill:           #f8fafc !important;
    --input-background-fill-focus:     #ffffff !important;
    --input-border-color:              #e2e8f0 !important;
    --input-placeholder-color:         #94a3b8 !important;
    --panel-background-fill:           #ffffff !important;
    --table-even-background-fill:      #f8fafc !important;
    --table-odd-background-fill:       #ffffff !important;
    --neutral-50:   #f8fafc !important;  --neutral-100: #f1f5f9 !important;
    --neutral-200:  #e2e8f0 !important;  --neutral-300: #cbd5e1 !important;
    --neutral-400:  #94a3b8 !important;  --neutral-500: #64748b !important;
    --neutral-600:  #475569 !important;  --neutral-700: #334155 !important;
    --neutral-800:  #1e293b !important;  --neutral-900: #0f172a !important;
    --background-fill-primary:         #ffffff !important;
    --background-fill-secondary:       #f8fafc !important;
}
html:not(.tm-dark) .block,
html:not(.tm-dark) .form,
html:not(.tm-dark) .padded,
html:not(.tm-dark) fieldset {
    background: #ffffff !important;
    color: #0f172a !important;
    border-color: #e2e8f0 !important;
}
html:not(.tm-dark) input[type=text],
html:not(.tm-dark) textarea,
html:not(.tm-dark) select {
    color: #0f172a !important;
    background: #f8fafc !important;
}

/* ── Responsive / Mobile ────────────────────────────────────────────────── */
@media (max-width: 900px) {
    /* Stack columns vertically */
    .gap, [class*="row"] { flex-wrap: wrap !important; }
    [class*="column"] {
        min-width: 100% !important;
        width: 100% !important;
        flex: 1 1 100% !important;
    }
    .tabitem { padding: 12px !important; }

    /* Gradio container full width */
    .gradio-container { padding: 0 !important; margin: 0 !important; max-width: 100% !important; }

    /* Header — move toggle below title, not overlapping */
    #tm-toggle {
        position: static !important;
        display: block !important;
        margin: 12px 0 0 auto !important;
        padding: 10px 20px !important;
        min-height: 44px !important;
        min-width: 90px !important;
        font-size: 0.85rem !important;
    }

    /* Tabs — horizontally scrollable, no wrap */
    .tab-nav {
        overflow-x: auto !important;
        overflow-y: hidden !important;
        white-space: nowrap !important;
        -webkit-overflow-scrolling: touch !important;
        border-radius: 0 !important;
        position: sticky !important;
        top: 0 !important;
        z-index: 100 !important;
    }
    .tab-nav button {
        font-size: 0.75rem !important;
        padding: 12px 16px !important;
        min-height: 44px !important;
    }

    /* Buttons — full width, finger-friendly (min 44px Apple HIG) */
    button.primary, button.secondary {
        width: 100% !important;
        padding: 16px 20px !important;
        font-size: 0.9rem !important;
        min-height: 48px !important;
        border-radius: 12px !important;
    }

    /* Inputs — comfortable on mobile */
    input[type=text], textarea, select {
        font-size: 16px !important;   /* prevents iOS zoom-on-focus */
        padding: 12px !important;
        min-height: 44px !important;
    }

    /* Collapse all two-column grids to single column */
    [style*="grid-template-columns:1fr 1fr"] {
        grid-template-columns: 1fr !important;
    }

    /* Toast — full width */
    #tm-toast {
        top: 12px !important; right: 12px !important;
        left: 12px !important; max-width: calc(100% - 24px) !important;
    }

    /* Impact stat banner */
    [style*="display:flex;align-items:center;gap:20px;font-family"] {
        flex-direction: column !important;
        gap: 8px !important;
        text-align: center !important;
    }

    /* Architecture flow boxes — stack */
    [style*="display:flex;align-items:center;justify-content:center;flex-wrap:wrap;gap:8px"] {
        flex-direction: column !important;
        align-items: stretch !important;
    }
}

@media (max-width: 480px) {
    .tabitem { padding: 8px !important; }
    .tab-nav button { font-size: 0.7rem !important; padding: 10px 12px !important; }
    /* Header banner — tighter on small phones */
    [style*="padding:30px 36px;border-radius:16px"] {
        padding: 18px 16px !important;
        border-radius: 0 !important;
    }
    [style*="font-size:2rem;font-weight:800;letter-spacing:-0.04em"] {
        font-size: 1.6rem !important;
    }
    [style*="font-size:0.9rem;margin-top:5px"] {
        font-size: 0.78rem !important;
    }
    /* Safe area padding for notched phones */
    html, body {
        padding-top: env(safe-area-inset-top) !important;
        padding-bottom: env(safe-area-inset-bottom) !important;
    }
}

/* ── Scrollbar ──────────────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border-2); border-radius: 2px; }

/* ── Dark mode: override Gradio's own CSS variable set ──────────────────── */
/* gr.themes.Soft() bakes in a light palette via these names.               */
/* Re-declaring them on html.tm-dark makes every Gradio component respond.  */
html.tm-dark {
    --body-background-fill:            #070c18 !important;
    --body-background-fill-secondary:  #0d1528 !important;
    --block-background-fill:           #0d1528 !important;
    --block-border-color:              rgba(255,255,255,0.06) !important;
    --block-border-width:              1px !important;
    --block-label-background-fill:     #111e33 !important;
    --block-label-border-color:        rgba(255,255,255,0.06) !important;
    --block-label-text-color:          #94a3b8 !important;
    --block-title-text-color:          #e2e8f0 !important;
    --block-info-text-color:           #94a3b8 !important;
    --border-color-primary:            rgba(255,255,255,0.06) !important;
    --border-color-accent:             rgba(255,255,255,0.12) !important;
    --border-color-accent-subdued:     rgba(255,255,255,0.06) !important;
    --color-accent:                    #60a5fa !important;
    --color-accent-soft:               rgba(96,165,250,0.08) !important;
    --input-background-fill:           #111e33 !important;
    --input-background-fill-focus:     #111e33 !important;
    --input-background-fill-hover:     #111e33 !important;
    --input-border-color:              rgba(255,255,255,0.06) !important;
    --input-border-color-focus:        #60a5fa !important;
    --input-border-color-hover:        rgba(255,255,255,0.12) !important;
    --input-placeholder-color:         #475569 !important;
    --panel-background-fill:           #0d1528 !important;
    --panel-border-color:              rgba(255,255,255,0.06) !important;
    --section-header-text-color:       #94a3b8 !important;
    --table-border-color:              rgba(255,255,255,0.06) !important;
    --table-even-background-fill:      #111e33 !important;
    --table-odd-background-fill:       #0d1528 !important;
    --neutral-50:   #070c18 !important;  --neutral-100: #0d1528 !important;
    --neutral-200:  #111e33 !important;  --neutral-300: rgba(255,255,255,0.08) !important;
    --neutral-400:  #475569 !important;  --neutral-500: #64748b !important;
    --neutral-600:  #94a3b8 !important;  --neutral-700: #cbd5e1 !important;
    --neutral-800:  #e2e8f0 !important;  --neutral-900: #f1f5f9 !important;
    --color-grey-50:  #070c18 !important; --color-grey-100: #0d1528 !important;
    --color-grey-200: #111e33 !important;
    --secondary-50: rgba(96,165,250,0.08) !important;
    --secondary-100: rgba(96,165,250,0.12) !important;
    --background-fill-primary:   #0d1528 !important;
    --background-fill-secondary: #111e33 !important;
}

/* ── Dark mode: Gradio component-level overrides ────────────────────────── */
/* These catch anything that ignores CSS variables and uses a hardcoded bg. */
html.tm-dark .block,
html.tm-dark .form,
html.tm-dark .gap,
html.tm-dark .padded,
html.tm-dark .panel,
html.tm-dark fieldset,
html.tm-dark .contain,
html.tm-dark .label-wrap,
html.tm-dark .wrap.default {
    background: var(--surface) !important;
    border-color: var(--border) !important;
    color: var(--text) !important;
}

/* File upload box */
html.tm-dark .upload-container,
html.tm-dark .file-preview-holder,
html.tm-dark .file-count,
html.tm-dark .dashed-border,
html.tm-dark [data-testid="upload-box"],
html.tm-dark .upload {
    background: var(--surface-2) !important;
    border-color: var(--border-2) !important;
    color: var(--text-2) !important;
}

/* Dropdown options popup */
html.tm-dark .options,
html.tm-dark ul.options {
    background: var(--surface) !important;
    border: 1px solid var(--border-2) !important;
    box-shadow: var(--shadow-lg) !important;
}
html.tm-dark .options li,
html.tm-dark .options > * {
    color: var(--text) !important;
    background: transparent !important;
}
html.tm-dark .options li:hover,
html.tm-dark .options > *:hover { background: var(--accent-bg) !important; }
html.tm-dark .options li.selected,
html.tm-dark .options > *.selected {
    background: var(--accent-bg) !important;
    color: var(--accent) !important;
}

/* Accordion inner content */
html.tm-dark .accordion-content,
html.tm-dark details > div,
html.tm-dark .open > .inner {
    background: var(--surface) !important;
    border-color: var(--border) !important;
}

/* Misc text that stays dark */
html.tm-dark span,
html.tm-dark p,
html.tm-dark div {
    color: inherit;
}
html.tm-dark .prose,
html.tm-dark .prose p { color: var(--text-2) !important; }

/* SVG icons in Gradio buttons / inputs */
html.tm-dark button svg,
html.tm-dark .icon svg {
    color: var(--text-2) !important;
    stroke: var(--text-2) !important;
}

"""

# ─────────────────────────────────────────────────────────────────────────────
# JavaScript — runs via demo.load(js=...) after page hydration.
# Uses MutationObserver to wire the #tm-toggle button that lives inside
# gr.HTML (which renders async). No onclick attribute needed — addEventListener
# is added programmatically so Gradio's HTML sanitiser can't block it.
# ─────────────────────────────────────────────────────────────────────────────

_THEME_JS = """
() => {
    // ── Apply all CSS variables directly on <html> via style.setProperty ──
    // Using inline styles means NO stylesheet can override them, regardless
    // of what Gradio's theme injects. This fixes white-on-white in light mode.
    const applyVars = (dark) => {
        const r = document.documentElement;
        const s = (k, v) => r.style.setProperty(k, v);

        if (dark) {
            s('--bg',           '#070c18');
            s('--surface',      '#0d1528');
            s('--surface-2',    '#111e33');
            s('--border',       'rgba(255,255,255,0.06)');
            s('--border-2',     'rgba(255,255,255,0.12)');
            s('--text',         '#e2e8f0');
            s('--text-2',       '#94a3b8');
            s('--text-3',       '#475569');
            s('--accent',       '#60a5fa');
            s('--accent-2',     '#3b82f6');
            s('--accent-bg',    'rgba(96,165,250,0.08)');
            s('--accent-glow',  'rgba(96,165,250,0.22)');
            s('--green',        '#34d399'); s('--green-2','#6ee7b7');
            s('--green-bg',     'rgba(52,211,153,0.09)');
            s('--green-bd',     'rgba(52,211,153,0.22)');
            s('--amber',        '#fbbf24'); s('--amber-2','#fde68a');
            s('--amber-bg',     'rgba(251,191,36,0.09)');
            s('--amber-bd',     'rgba(251,191,36,0.22)');
            s('--red',          '#f87171'); s('--red-2','#fca5a5');
            s('--red-bg',       'rgba(248,113,113,0.09)');
            s('--red-bd',       'rgba(248,113,113,0.22)');
            s('--info',         '#38bdf8');
            s('--info-bg',      'rgba(56,189,248,0.08)');
            s('--info-bd',      'rgba(56,189,248,0.2)');
            s('--shadow',       '0 1px 4px rgba(0,0,0,0.5),0 0 0 1px rgba(255,255,255,0.04)');
            s('--shadow-md',    '0 4px 20px rgba(0,0,0,0.55),0 0 0 1px rgba(255,255,255,0.05)');
            // Gradio overrides
            s('--body-background-fill',           '#070c18');
            s('--block-background-fill',          '#0d1528');
            s('--block-label-text-color',         '#94a3b8');
            s('--block-title-text-color',         '#e2e8f0');
            s('--block-info-text-color',          '#94a3b8');
            s('--input-background-fill',          '#111e33');
            s('--input-border-color',             'rgba(255,255,255,0.06)');
            s('--color-accent',                   '#60a5fa');
            s('--background-fill-primary',        '#0d1528');
            s('--background-fill-secondary',      '#111e33');
            s('--neutral-900',  '#f1f5f9'); s('--neutral-800','#e2e8f0');
            s('--neutral-700',  '#cbd5e1'); s('--neutral-600','#94a3b8');
            s('--neutral-500',  '#64748b'); s('--neutral-400','#475569');
            s('--neutral-100',  '#0d1528'); s('--neutral-50', '#070c18');
        } else {
            s('--bg',           '#f1f5f9');
            s('--surface',      '#ffffff');
            s('--surface-2',    '#f8fafc');
            s('--border',       '#e2e8f0');
            s('--border-2',     '#cbd5e1');
            s('--text',         '#0f172a');
            s('--text-2',       '#475569');
            s('--text-3',       '#94a3b8');
            s('--accent',       '#2563eb');
            s('--accent-2',     '#1d4ed8');
            s('--accent-bg',    '#eff6ff');
            s('--accent-glow',  'rgba(37,99,235,0.18)');
            s('--green',        '#059669'); s('--green-2','#34d399');
            s('--green-bg',     '#f0fdf4'); s('--green-bd','#6ee7b7');
            s('--amber',        '#d97706'); s('--amber-2','#fbbf24');
            s('--amber-bg',     '#fffbeb'); s('--amber-bd','#fde68a');
            s('--red',          '#dc2626'); s('--red-2','#f87171');
            s('--red-bg',       '#fef2f2'); s('--red-bd','#fecaca');
            s('--info',         '#0ea5e9');
            s('--info-bg',      '#f0f9ff'); s('--info-bd','#bae6fd');
            s('--shadow',       '0 1px 3px rgba(0,0,0,0.05),0 0 0 1px rgba(0,0,0,0.03)');
            s('--shadow-md',    '0 4px 16px rgba(0,0,0,0.08),0 0 0 1px rgba(0,0,0,0.04)');
            // Gradio overrides — force light values so text is always readable
            s('--body-background-fill',           '#f1f5f9');
            s('--block-background-fill',          '#ffffff');
            s('--block-label-text-color',         '#475569');
            s('--block-title-text-color',         '#0f172a');
            s('--block-info-text-color',          '#475569');
            s('--input-background-fill',          '#f8fafc');
            s('--input-border-color',             '#e2e8f0');
            s('--color-accent',                   '#2563eb');
            s('--background-fill-primary',        '#ffffff');
            s('--background-fill-secondary',      '#f8fafc');
            s('--neutral-900',  '#0f172a'); s('--neutral-800','#1e293b');
            s('--neutral-700',  '#334155'); s('--neutral-600','#475569');
            s('--neutral-500',  '#64748b'); s('--neutral-400','#94a3b8');
            s('--neutral-100',  '#f1f5f9'); s('--neutral-50', '#f8fafc');
        }
    };

    // ── Theme toggle ───────────────────────────────────────────────────────
    const saved  = localStorage.getItem('tm-theme');
    const osDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const isDark = saved === 'dark' || (!saved && osDark);
    document.documentElement.classList.toggle('tm-dark', isDark);
    applyVars(isDark);

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
            applyVars(dark);
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
            const n = new Notification(heading, { body, icon: '' });
            n.onclick = () => { window.focus(); n.close(); };
        }
    };

    // Poll instead of MutationObserver — Gradio can replace the #tm-status
    // DOM node entirely, orphaning any observer attached to the old element.
    // A 1.5 s poll always reads the live element from the DOM.
    let _tmLast     = '';
    let _tmNotified = false;
    setInterval(() => {
        const el = document.getElementById('tm-status');
        if (!el) return;
        const txt = (el.innerText || el.textContent || '').trim();
        if (txt === _tmLast) return;
        _tmLast = txt;

        // New run starting — reset so we notify again when it finishes
        if (/Step [1-4]\/4/.test(txt) || txt.includes('Reading your medical')) {
            _tmNotified = false;
            return;
        }
        if (_tmNotified) return;

        if (txt.includes('Matching complete')) {
            _tmNotified = true;
            showToast('✅', 'TrialMatch — Done!',
                'Matching complete. Click ✨ Generate Reasoning & Emails to enrich results.', false);
        } else if (txt.includes('Analysis complete')) {
            _tmNotified = true;
            showToast('✅', 'TrialMatch — Enrichment Done!',
                'Reasoning chains and email drafts are ready.', false);
        } else if (txt.includes('ERROR:')) {
            _tmNotified = true;
            showToast('❌', 'TrialMatch — Error',
                'An error occurred. Check the status box for details.', true);
        }
    }, 1500);

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
           padding:8px 18px;font-size:0.78rem;font-weight:600;
           font-family:system-ui,sans-serif;letter-spacing:0.04em;
           min-height:38px;min-width:80px;
           -webkit-tap-highlight-color:transparent;
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
        f'align-items:center;margin-bottom:4px;">'
        f'<span style="font-size:0.69rem;font-weight:700;color:var(--text-3);'
        f'text-transform:uppercase;letter-spacing:0.1em;">Match Confidence</span>'
        f'<span style="font-size:0.92rem;font-weight:800;color:{bar_color};">'
        f'{confidence}%</span></div>'
        f'<div style="font-size:0.71rem;color:var(--text-3);margin-bottom:8px;font-style:italic;">'
        f'Confidence = % of eligibility criteria this patient appears to meet</div>'
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


def _context_card_html(m):
    """One-line context card: what this trial studies and why it matters to this patient."""
    conditions = m.get("conditions", [])
    phase      = m.get("phase", "")
    verdict    = m.get("verdict", "MATCH")

    cond_str = " & ".join(c for c in conditions[:2] if c) if conditions else ""

    phase_label = ""
    if phase and phase not in ("Not specified", ""):
        p = phase.replace("PHASE", "Phase ").replace("_", " ").strip()
        phase_label = f" &middot; {p}"

    if cond_str:
        about = f'Investigating new treatments for <strong style="color:var(--text);">{cond_str}</strong>{phase_label}'
    else:
        about = f"Clinical research trial{phase_label}"

    why = ("Your profile appears to meet the eligibility requirements for this study."
           if verdict == "MATCH"
           else "Additional pre-screening may confirm your eligibility.")

    return (
        f'<div style="background:var(--info-bg);border:1px solid var(--info-bd);'
        f'border-left:3px solid var(--info);padding:10px 14px;border-radius:8px;'
        f'margin:0 0 14px;font-size:0.83rem;font-family:system-ui,sans-serif;">'
        f'<span style="color:var(--info);font-weight:700;">🔬 What this trial studies: </span>'
        f'<span style="color:var(--text-2);">{about}. {why}</span>'
        f'</div>'
    )


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

        nct_id          = m["nct_id"]
        reason          = m.get("reason", "")
        next_step       = m.get("next_step", "")
        reasoning_chain = m.get("reasoning_chain", "").strip()
        context_card    = _context_card_html(m)

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

        # ── Reasoning chain (collapsible) ────────────────────────────────────
        if reasoning_chain:
            steps = [s.strip() for s in reasoning_chain.split("\n") if s.strip()]
            steps_html = "".join(
                f'<div style="display:flex;gap:10px;align-items:flex-start;'
                f'padding:7px 0;border-bottom:1px solid var(--border);">'
                f'<span style="color:var(--accent);font-weight:700;font-size:0.78rem;'
                f'flex-shrink:0;padding-top:1px;min-width:18px;">'
                f'{i+1}.</span>'
                f'<span style="color:var(--text-2);font-size:0.82rem;line-height:1.55;">'
                f'{step.lstrip("0123456789. ")}</span>'
                f'</div>'
                for i, step in enumerate(steps)
            )
            reasoning_html = (
                f'<details style="margin:14px 0 2px;">'
                f'<summary style="cursor:pointer;list-style:none;display:flex;'
                f'align-items:center;gap:8px;padding:9px 14px;'
                f'background:var(--surface-2);border:1px solid var(--border);'
                f'border-radius:8px;user-select:none;">'
                f'<span style="font-size:0.95rem;">🧠</span>'
                f'<span style="font-weight:700;color:var(--accent);font-size:0.82rem;">'
                f'Show Gemma 4 reasoning</span>'
                f'<span style="color:var(--text-3);font-size:0.72rem;margin-left:auto;">'
                f'{len(steps)} step{"s" if len(steps)!=1 else ""} · Safety &amp; Trust</span>'
                f'</summary>'
                f'<div style="background:var(--surface-2);border:1px solid var(--border);'
                f'border-top:none;border-radius:0 0 8px 8px;padding:14px 16px;">'
                f'<div style="font-size:0.7rem;font-weight:700;color:var(--text-3);'
                f'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;'
                f'display:flex;align-items:center;gap:8px;">'
                f'<span>🤖 Gemma 4 · Step-by-step eligibility evaluation</span>'
                f'<span style="background:var(--accent-bg);color:var(--accent);'
                f'padding:1px 7px;border-radius:10px;font-size:0.65rem;">AI-generated</span>'
                f'</div>'
                f'{steps_html}'
                f'<div style="margin-top:10px;padding-top:10px;border-top:1px solid var(--border);'
                f'color:var(--text-3);font-size:0.72rem;line-height:1.5;">'
                f'This reasoning was generated by Gemma 4 running locally via Ollama. '
                f'It reflects the model\'s evaluation and should be verified by a clinician.'
                f'</div>'
                f'</div>'
                f'</details>'
            )
        else:
            reasoning_html = (
                f'<div style="margin:14px 0 2px;padding:10px 14px;'
                f'background:var(--surface-2);border:1px solid var(--border);'
                f'border-radius:8px;display:flex;align-items:center;gap:9px;">'
                f'<span style="font-size:1rem;">🧠</span>'
                f'<span style="color:var(--text-3);font-size:0.81rem;font-style:italic;">'
                f'Gemma 4 step-by-step reasoning — click '
                f'<strong style="color:var(--text-2);font-style:normal;">'
                f'✨ Generate Reasoning &amp; Emails</strong> above to reveal how this verdict was reached'
                f'</span></div>'
            )

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
    {context_card}{reason_html}{table_html}{ns_html}{reasoning_html}{contact_html}
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
    """Fast check: Ollama running + model installed. No inference call."""
    from utils import MODEL
    rows = []

    ollama_version = ""
    try:
        v = requests.get("http://localhost:11434/api/version", timeout=5)
        ollama_version = v.json().get("version", "")
    except Exception:
        pass

    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        resp.raise_for_status()
        ver_label = f" v{ollama_version}" if ollama_version else ""
        rows.append(_check_row("ok", f"Ollama{ver_label} — running"))

        models_data = resp.json().get("models", [])
        model_entry = next((m for m in models_data if MODEL in m.get("name", "")), None)
        if model_entry:
            size_gb = model_entry.get("size", 0) / (1024 ** 3)
            details = model_entry.get("details", {})
            quant   = details.get("quantization_level", "")
            params  = details.get("parameter_size", "")
            info    = "  ·  ".join(filter(None, [params, quant, f"{size_gb:.1f} GB on disk"]))
            rows.append(_check_row("ok", f"{MODEL}  ·  {info}"))
            rows.append(
                f'<div style="padding:4px 14px 12px 44px;font-size:0.79rem;'
                f'color:var(--text-3);font-family:system-ui,sans-serif;line-height:1.55;">'
                f'Running Gemma 4 locally via Ollama — no cloud, no API cost, '
                f'no data leaving this machine. Full analysis: ~7–10 min on CPU.</div>'
            )
        else:
            installed = [m.get("name", "") for m in models_data]
            rows.append(_check_row("error", f"{MODEL} not found — run: ollama pull {MODEL}"))
            if installed:
                rows.append(
                    f'<p style="font-size:0.82rem;color:var(--text-3);margin:0 0 4px 44px;'
                    f'font-family:system-ui,sans-serif;">Installed: {", ".join(installed)}</p>'
                )

    except requests.exceptions.ConnectionError:
        rows.append(_check_row("error", "Ollama is NOT running — run: ollama serve"))
    except Exception as e:
        rows.append(_check_row("warn", f"Could not reach Ollama: {e}"))

    return f'<div style="padding:4px;">{"".join(rows)}</div>'


def run_speed_test():
    """Optional live inference speed test — takes 30-60 s on CPU."""
    import ollama as _ollama
    from utils import MODEL
    rows = []

    rows.append(
        f'<div style="padding:8px 14px 8px 44px;font-size:0.81rem;'
        f'color:var(--text-3);font-style:italic;font-family:system-ui,sans-serif;">'
        f'Running live speed test — loading model into RAM, may take 30–60 s…</div>'
    )
    try:
        t0     = time.time()
        stream = _ollama.chat(
            model   = MODEL,
            messages= [{"role": "user", "content": "List 3 fruits."}],
            stream  = True,
            think   = False,
            options = {"num_predict": 25},
        )
        resp_text  = ""
        last_chunk = None
        for chunk in stream:
            if chunk.message.content:
                resp_text += chunk.message.content
            last_chunk = chunk
        elapsed = time.time() - t0

        if (last_chunk
                and getattr(last_chunk, "eval_count",    None)
                and getattr(last_chunk, "eval_duration", None)
                and last_chunk.eval_duration > 0):
            tps       = last_chunk.eval_count / (last_chunk.eval_duration / 1e9)
            tok_count = last_chunk.eval_count
        else:
            tok_count = max(1, len(resp_text) // 4)
            tps       = tok_count / elapsed if elapsed > 0 else 0

        rows.append(_check_row(
            "ok",
            f"Inference speed: {tps:.1f} tok/s  ·  {tok_count} tokens in {elapsed:.1f}s  ·  CPU-only"
        ))

    except Exception as e:
        err = str(e).lower()
        if any(k in err for k in ("memory", "system memory", "out of memory")):
            rows.append(_check_row(
                "warn",
                "Speed test skipped — not enough free RAM (~10 GB needed). Close other apps first."
            ))
        else:
            rows.append(_check_row("warn", f"Speed test failed: {e}"))

    return f'<div style="padding:4px;">{"".join(rows)}</div>'


# ─────────────────────────────────────────────────────────────────────────────
# Timing helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_time(s):
    if s < 1:
        return f"{s*1000:.0f}ms"
    if s < 60:
        return f"{s:.1f}s"
    m, sec = divmod(int(s), 60)
    return f"{m}m {sec:02d}s"


def _format_timing_html(timings):
    """
    Render an ⚡ Pipeline Performance card showing per-step durations with
    proportional bars. Prepended to results_html so judges see it immediately.
    """
    steps = []

    pdf      = timings.get("pdf_read",      0)
    ext      = timings.get("ai_extract",    0)
    rsn      = timings.get("ai_reason",     0)
    fetch    = timings.get("api_fetch",     0)
    match    = timings.get("ai_match",      0)
    n_t      = timings.get("trial_count",   0)
    reasoning= timings.get("ai_reasoning")
    email    = timings.get("ai_email")
    trans    = timings.get("ai_translate")
    total    = timings.get("total",         0)

    if pdf      > 0: steps.append(("📄", "PDF Reading",                     pdf,      "var(--text-2)"))
    if ext      > 0: steps.append(("🧬", "AI Profile Extraction",           ext,      "var(--accent)"))
    if rsn      > 0: steps.append(("🩺", "AI Clinical Reasoning",           rsn,      "var(--accent)"))
    if fetch    > 0: steps.append(("🔍", "ClinicalTrials.gov API",          fetch,    "var(--info)"))
    if match    > 0:
        label = f"AI Trial Matching ({n_t} trial{'s' if n_t != 1 else ''})"
        steps.append(("🤖", label, match, "var(--accent)"))
    if reasoning: steps.append(("🧠", "AI Reasoning Chains (MATCH/PARTIAL)", reasoning, "var(--accent)"))
    if email:     steps.append(("📧", "AI Email Draft",                     email,    "var(--accent)"))
    if trans:     steps.append(("🌐", "AI Translation",                     trans,    "var(--accent)"))

    if not steps:
        return ""

    max_t = max(s[2] for s in steps) or 1

    rows_html = ""
    for emoji, label, secs, color in steps:
        pct    = max(2, int((secs / max_t) * 100))
        t_str  = _fmt_time(secs)
        is_ai  = color == "var(--accent)"
        badge  = (
            '<span style="background:var(--accent-bg);color:var(--accent);'
            'font-size:0.65rem;font-weight:700;padding:1px 6px;border-radius:10px;'
            'letter-spacing:0.04em;margin-left:6px;">AI</span>'
            if is_ai else ""
        )
        rows_html += (
            f'<div style="display:flex;align-items:center;gap:12px;padding:7px 0;'
            f'border-bottom:1px solid var(--border);">'
            f'  <span style="font-size:1rem;flex-shrink:0;">{emoji}</span>'
            f'  <div style="width:200px;flex-shrink:0;display:flex;align-items:center;">'
            f'    <span style="color:var(--text-2);font-size:0.81rem;">{label}</span>{badge}'
            f'  </div>'
            f'  <div style="flex:1;background:var(--surface-2);border-radius:6px;'
            f'              height:8px;overflow:hidden;border:1px solid var(--border);">'
            f'    <div style="width:{pct}%;height:100%;border-radius:6px;'
            f'                background:linear-gradient(90deg,{color}88,{color});'
            f'                animation:confGrow 0.9s cubic-bezier(0.16,1,0.3,1) forwards;'
            f'                --pct:{pct}%;"></div>'
            f'  </div>'
            f'  <div style="width:64px;text-align:right;font-weight:700;color:var(--text);'
            f'              font-size:0.85rem;flex-shrink:0;">{t_str}</div>'
            f'</div>'
        )

    # Total colour: green <10 min, amber 10–20 min, red >20 min
    if total < 600:
        total_color = "var(--green)"
    elif total < 1200:
        total_color = "var(--amber)"
    else:
        total_color = "var(--red)"

    return (
        f'<div style="font-family:system-ui,sans-serif;background:var(--surface);'
        f'border:1.5px solid var(--border);border-radius:14px;'
        f'padding:20px 24px;margin-bottom:20px;">'

        # Header row
        f'<div style="display:flex;align-items:center;justify-content:space-between;'
        f'            flex-wrap:wrap;gap:10px;margin-bottom:18px;">'
        f'  <div style="display:flex;align-items:center;gap:10px;">'
        f'    <span style="font-size:1.4rem;">⚡</span>'
        f'    <div>'
        f'      <div style="font-weight:800;color:var(--text);font-size:0.92rem;">Pipeline Performance</div>'
        f'      <div style="color:var(--text-3);font-size:0.74rem;margin-top:2px;">'
        f'        Gemma 4 running locally via Ollama — zero cloud AI, zero data transmitted'
        f'      </div>'
        f'    </div>'
        f'  </div>'
        f'  <div style="background:var(--surface-2);border:1.5px solid {total_color};'
        f'              border-radius:20px;padding:6px 16px;display:flex;align-items:center;gap:7px;">'
        f'    <span style="color:{total_color};font-size:0.78rem;font-weight:800;">⏱ Total</span>'
        f'    <span style="color:{total_color};font-weight:800;font-size:0.9rem;">{_fmt_time(total)}</span>'
        f'  </div>'
        f'</div>'

        # Step rows
        f'<div style="margin-bottom:16px;">{rows_html}</div>'

        # Footer badges
        f'<div style="display:flex;gap:8px;flex-wrap:wrap;padding-top:4px;">'
        f'  <span style="background:var(--accent-bg);color:var(--accent);padding:3px 10px;'
        f'               border-radius:20px;font-size:0.72rem;font-weight:700;'
        f'               border:1px solid var(--accent);">🤖 Gemma 4 (4B · e4b)</span>'
        f'  <span style="background:var(--surface-2);color:var(--text-2);padding:3px 10px;'
        f'               border-radius:20px;font-size:0.72rem;font-weight:600;'
        f'               border:1px solid var(--border);">🦙 Ollama</span>'
        f'  <span style="background:var(--surface-2);color:var(--text-2);padding:3px 10px;'
        f'               border-radius:20px;font-size:0.72rem;font-weight:600;'
        f'               border:1px solid var(--border);">💻 CPU only</span>'
        f'  <span style="background:var(--green-bg);color:var(--green);padding:3px 10px;'
        f'               border-radius:20px;font-size:0.72rem;font-weight:700;'
        f'               border:1px solid var(--green-bd);">🔒 No GPU · No Cloud · 100% Local</span>'
        f'</div>'
        f'</div>'
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main pipeline  (generator — yields 6-tuples)
# Extra two outputs: enrich_btn visibility update + enrich_state value
# ─────────────────────────────────────────────────────────────────────────────

def run_trialmatch(pdf_file, condition, language):
    _no_change = gr.update()   # sentinel: leave component unchanged

    if pdf_file is None:
        yield _status_html("⚠  Please upload a PDF file before running.", warn=True), "", "", "", gr.update(), None
        return
    if not condition or not condition.strip():
        yield _status_html("⚠  Please enter a condition keyword (e.g. 'type 2 diabetes').", warn=True), "", "", "", gr.update(), None
        return

    condition        = condition.strip()
    language         = language or "English"
    t_pipeline_start = time.time()
    _timings         = {}

    if isinstance(pdf_file, str):
        pdf_path = pdf_file
    elif hasattr(pdf_file, "name"):
        pdf_path = pdf_file.name
    elif isinstance(pdf_file, dict):
        pdf_path = pdf_file.get("path") or pdf_file.get("name") or ""
    else:
        pdf_path = str(pdf_file)

    if not pdf_path:
        yield _status_html("ERROR: Could not determine the uploaded file path."), "", "", "", gr.update(), None
        return

    yield (
        _status_html(
            "Step 1/4 — Reading your medical records and running clinical reasoning...\n"
            "(first run may take 2–3 minutes while the model loads)"
        ),
        "", "", "", gr.update(), None,
    )
    try:
        profile_data = extract_patient_profile(pdf_path)
    except Exception as e:
        yield _status_html(f"ERROR reading PDF: {e}"), _msg_html(f"Error: {e}", "error"), "", "", gr.update(), None
        return

    if isinstance(profile_data, str):
        yield _status_html(profile_data), _msg_html(profile_data, "error"), "", "", gr.update(), None
        return

    patient_profile    = profile_data["raw_extraction"]
    clinical_reasoning = profile_data["clinical_reasoning"]
    key_flags          = profile_data["key_flags"]
    used_vision        = profile_data.get("used_vision", False)
    _timings.update(profile_data.get("step_timings", {}))

    _mode_label = "ClinicalTrials.gov 🌐 online" if is_online() else f"local database 🔌 offline ({_DB_TRIAL_COUNT:,} trials)"
    t1 = _timings.get("pdf_read", 0) + _timings.get("ai_extract", 0)
    _vision_note = "  ·  📷 Gemma 4 Vision used (scanned PDF)" if used_vision else ""
    yield _status_html(
        f"Step 2/4 — Searching {_mode_label} for recruiting trials...\n"
        f"(Step 1 completed in {_fmt_time(t1)}{_vision_note})"
    ), "", "", "", gr.update(), None
    t0 = time.time()
    try:
        trials = fetch_trials(condition, max_results=3)
    except Exception as e:
        yield _status_html(f"ERROR fetching trials: {e}"), _msg_html(f"Error: {e}", "error"), "", "", gr.update(), None
        return
    _timings["api_fetch"] = time.time() - t0

    if not trials:
        msg = ("No recruiting trials found for this condition.\n\n"
               "• Try a broader keyword (e.g. 'diabetes')\n"
               "• Try an alternative name for the condition\n"
               "• Check your internet connection")
        yield _status_html("Search complete.", done=True), _msg_html(msg), "", "", gr.update(), None
        return

    matches      = []
    total        = len(trials)
    t_match_acc  = 0.0
    t_last_match = 0.0
    for i, trial in enumerate(trials):
        trial_title = trial.get("title", f"Trial {i + 1}")
        short       = trial_title[:72] + ("…" if len(trial_title) > 72 else "")
        prev_note   = f"\n(Trial {i} matched in {_fmt_time(t_last_match)})" if i > 0 else ""
        yield _status_html(
            f"Step 3/4 — Matching trial {i + 1} of {total}:\n{short}{prev_note}"
        ), "", "", "", gr.update(), None
        t0 = time.time()
        try:
            result = match_patient_to_trial(patient_profile, clinical_reasoning, trial)
            if result["verdict"] in ("MATCH", "PARTIAL"):
                matches.append(result)
        except Exception:
            pass
        t_last_match  = time.time() - t0
        t_match_acc  += t_last_match
    _timings["ai_match"]    = t_match_acc
    _timings["trial_count"] = total

    if not matches:
        msg = (f"No qualifying trials found among {total} reviewed.\n\n"
               "• Try a broader condition keyword\n"
               "• New trials open regularly — try again in a few days\n"
               "• Consult your doctor about trials they may know of")
        yield _status_html("Analysis complete.", done=True), _msg_html(msg), "", "", gr.update(), None
        return

    matches = sorted(matches, key=lambda m: m.get("confidence_score", 0), reverse=True)

    yield _status_html(
        f"Step 4/4 — Building results…\n"
        f"(Matching {total} trial(s) completed in {_fmt_time(_timings['ai_match'])})"
    ), "", "", "", gr.update(), None

    results_html_str = _format_results_html(matches, total, key_flags)

    # ── Translation runs automatically if the user selected a language ────────
    translated_html = ""
    if language != "English":
        yield _status_html(
            f"🌐 Translating results to {language}…\n"
            f"(Matching {total} trial(s) completed in {_fmt_time(_timings['ai_match'])})"
        ), results_html_str, "", "", gr.update(), None
        t0 = time.time()
        try:
            t_matches       = translate_matches(matches, language)
            translated_html = _format_translated_html(t_matches, total, language, key_flags)
        except Exception as e:
            translated_html = _msg_html(f"Translation error: {e}", "error")
        _timings["ai_translate"] = time.time() - t0

    _timings["total"] = time.time() - t_pipeline_start
    timing_card       = _format_timing_html(_timings)

    if used_vision:
        _vision_banner = (
            '<div style="display:flex;align-items:center;gap:10px;padding:10px 16px;'
            'margin-bottom:16px;background:linear-gradient(135deg,#0f172a,#1e293b);'
            'border:1px solid #334155;border-radius:10px;font-family:system-ui,sans-serif;">'
            '<span style="font-size:1.4rem;">📷</span>'
            '<div>'
            '<div style="color:#e2e8f0;font-weight:600;font-size:0.88rem;">'
            'Gemma 4 Vision — Scanned PDF processed locally</div>'
            '<div style="color:#94a3b8;font-size:0.78rem;margin-top:2px;">'
            'No text layer detected · Gemma 4 read the page images directly via Ollama · '
            'Zero data sent to any external service</div>'
            '</div></div>'
        )
        results_html_str = _vision_banner + results_html_str

    # Store everything the enrichment function needs
    enrich_state = {
        "matches":          matches,
        "patient_profile":  patient_profile,
        "total":            total,
        "key_flags":        key_flags,
        "language":         language,
        "timings":          _timings,
        "timing_card":      timing_card,
    }

    _vision_done = "  ·  📷 Vision (scanned PDF)" if used_vision else ""
    yield (
        _status_html(
            "Matching complete — click ✨ Generate Reasoning & Emails to enrich results.\n"
            f"(Total pipeline: {_fmt_time(_timings['total'])}  ·  "
            f"Profile: {_fmt_time(t1)}  ·  "
            f"Matching: {_fmt_time(_timings['ai_match'])}{_vision_done})",
            done=True,
        ),
        timing_card + results_html_str,
        "",
        translated_html,
        gr.update(interactive=True),
        enrich_state,
    )

# ─────────────────────────────────────────────────────────────────────────────
# On-demand enrichment  (generator — yields 5-tuples)
# Triggered by the "Generate Reasoning & Emails" button after main pipeline.
# ─────────────────────────────────────────────────────────────────────────────

def generate_enrichment(state):
    if not state or not state.get("matches"):
        yield _status_html("No results to enrich — run the analysis first.", warn=True), gr.update(), gr.update(), gr.update(), gr.update()
        return

    matches         = state["matches"]
    patient_profile = state["patient_profile"]
    total           = state["total"]
    key_flags       = state["key_flags"]
    language        = state["language"]
    _timings        = dict(state["timings"])   # copy so we can add to it
    t_enrich_start  = time.time()

    results_html_str = _format_results_html(matches, total, key_flags)

    # ── Reasoning chains ─────────────────────────────────────────────────────
    t0 = time.time()
    for idx, m in enumerate(matches):
        short = m["trial_title"][:55] + ("…" if len(m["trial_title"]) > 55 else "")
        yield (
            _status_html(f"🧠 Reasoning {idx + 1}/{len(matches)}: {short}"),
            gr.update(),   # results unchanged while computing
            gr.update(),
            gr.update(),
            gr.update(interactive=False),
        )
        m["reasoning_chain"] = generate_reasoning_chain(
            patient_profile,
            m.get("eligibility_criteria", ""),
            m["verdict"],
            m.get("confidence_score", 50),
        )
        results_html_str = _format_results_html(matches, total, key_flags)
    _timings["ai_reasoning"] = time.time() - t0

    # ── Email drafts ──────────────────────────────────────────────────────────
    emails_text = ""
    match_only  = [m for m in matches if m["verdict"] == "MATCH"]
    if match_only:
        yield (
            _status_html("📧 Drafting inquiry emails for MATCH verdicts…"),
            gr.update(), gr.update(), gr.update(),
            gr.update(interactive=False),
        )
        email_parts = []
        t0 = time.time()
        for m in match_only:
            try:
                email_text = generate_inquiry_email(patient_profile, m)
                email_parts.append(
                    f"{'─' * 64}\nTrial: {m['trial_title']}\nNCT:   {m['nct_id']}\n\n{email_text}"
                )
            except Exception as e:
                email_parts.append(f"Could not draft email for {m['trial_title']}: {e}")
        _timings["ai_email"] = time.time() - t0
        emails_text = "\n\n".join(email_parts)
    else:
        emails_text = ("No full MATCH verdicts — only PARTIAL matches found.\n"
                       "Emails are drafted for MATCH verdicts only.\n"
                       "Consult your doctor for PARTIAL matches.")

    _timings["total"] = _timings.get("total", 0) + (time.time() - t_enrich_start)
    timing_card       = _format_timing_html(_timings)

    yield (
        _status_html("Analysis complete.", done=True),
        timing_card + results_html_str,
        emails_text,
        gr.update(),               # translation already set by main pipeline — leave it
        gr.update(interactive=False),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Placeholder HTML (uses CSS variables → dark-mode aware)
# ─────────────────────────────────────────────────────────────────────────────

_HEAD_HTML = """
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="TrialMatch">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="theme-color" content="#060f24">
<meta name="description" content="AI clinical trial matching — private, local, offline-capable">
"""

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
# Privacy & Trust panel HTML
# ─────────────────────────────────────────────────────────────────────────────

_PRIVACY_HTML = """
<div style="font-family:system-ui,sans-serif;max-width:900px;margin:0 auto;">

  <!-- Hero banner -->
  <div style="background:linear-gradient(135deg,#022c22 0%,#064e3b 55%,#065f46 100%);
              border-radius:16px;padding:32px 36px;margin-bottom:28px;text-align:center;
              box-shadow:0 12px 40px rgba(0,0,0,0.35);">
    <div style="font-size:2.8rem;margin-bottom:14px;">🔒</div>
    <div style="color:#fff;font-size:1.5rem;font-weight:800;letter-spacing:-0.03em;margin-bottom:10px;">
      Your medical data never leaves your device
    </div>
    <div style="color:rgba(255,255,255,0.72);font-size:0.92rem;line-height:1.6;max-width:580px;margin:0 auto;">
      TrialMatch runs the entire AI pipeline locally on your computer.
      Your records, your diagnosis, your analysis — all processed offline.
    </div>
  </div>

  <!-- Data flow: two columns -->
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:28px;">

    <!-- Stays on device -->
    <div style="background:var(--green-bg);border:1.5px solid var(--green-bd);
                border-left:4px solid var(--green);border-radius:14px;padding:24px;">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:18px;">
        <span style="font-size:1.5rem;">💻</span>
        <div>
          <div style="font-weight:800;color:var(--green);font-size:0.8rem;
                      text-transform:uppercase;letter-spacing:0.08em;">Stays on your device</div>
          <div style="color:var(--text-3);font-size:0.75rem;margin-top:2px;">Never transmitted anywhere</div>
        </div>
      </div>
      <div style="display:flex;flex-direction:column;gap:11px;">
        <div style="display:flex;gap:11px;align-items:flex-start;">
          <span style="color:var(--green);font-weight:700;flex-shrink:0;margin-top:1px;">✓</span>
          <div>
            <div style="font-weight:600;color:var(--text);font-size:0.87rem;">Your PDF medical record</div>
            <div style="color:var(--text-3);font-size:0.78rem;margin-top:2px;">Read locally by PyMuPDF — never uploaded</div>
          </div>
        </div>
        <div style="display:flex;gap:11px;align-items:flex-start;">
          <span style="color:var(--green);font-weight:700;flex-shrink:0;margin-top:1px;">✓</span>
          <div>
            <div style="font-weight:600;color:var(--text);font-size:0.87rem;">Extracted patient profile</div>
            <div style="color:var(--text-3);font-size:0.78rem;margin-top:2px;">Diagnosis, medications, lab values, age — all local</div>
          </div>
        </div>
        <div style="display:flex;gap:11px;align-items:flex-start;">
          <span style="color:var(--green);font-weight:700;flex-shrink:0;margin-top:1px;">✓</span>
          <div>
            <div style="font-weight:600;color:var(--text);font-size:0.87rem;">All Gemma 4 AI processing</div>
            <div style="color:var(--text-3);font-size:0.78rem;margin-top:2px;">Runs via Ollama at localhost:11434 — no cloud AI</div>
          </div>
        </div>
        <div style="display:flex;gap:11px;align-items:flex-start;">
          <span style="color:var(--green);font-weight:700;flex-shrink:0;margin-top:1px;">✓</span>
          <div>
            <div style="font-weight:600;color:var(--text);font-size:0.87rem;">Matching results & confidence scores</div>
            <div style="color:var(--text-3);font-size:0.78rem;margin-top:2px;">MATCH / PARTIAL / NO verdicts computed locally</div>
          </div>
        </div>
        <div style="display:flex;gap:11px;align-items:flex-start;">
          <span style="color:var(--green);font-weight:700;flex-shrink:0;margin-top:1px;">✓</span>
          <div>
            <div style="font-weight:600;color:var(--text);font-size:0.87rem;">Clinical reasoning summary</div>
            <div style="color:var(--text-3);font-size:0.78rem;margin-top:2px;">Severity, stability, key flags — generated on-device</div>
          </div>
        </div>
        <div style="display:flex;gap:11px;align-items:flex-start;">
          <span style="color:var(--green);font-weight:700;flex-shrink:0;margin-top:1px;">✓</span>
          <div>
            <div style="font-weight:600;color:var(--text);font-size:0.87rem;">Email drafts</div>
            <div style="color:var(--text-3);font-size:0.78rem;margin-top:2px;">Written by local Gemma 4 — not sent automatically</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Sent to internet -->
    <div style="background:var(--info-bg);border:1.5px solid var(--info-bd);
                border-left:4px solid var(--info);border-radius:14px;padding:24px;">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:18px;">
        <span style="font-size:1.5rem;">🌐</span>
        <div>
          <div style="font-weight:800;color:var(--info);font-size:0.8rem;
                      text-transform:uppercase;letter-spacing:0.08em;">Sent to the internet</div>
          <div style="color:var(--text-3);font-size:0.75rem;margin-top:2px;">One call only — no personal data</div>
        </div>
      </div>
      <!-- Single item -->
      <div style="background:var(--surface);border:1px solid var(--border);
                  border-radius:10px;padding:16px;margin-bottom:16px;">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
          <span style="font-size:1rem;">🔍</span>
          <span style="font-weight:700;color:var(--text);font-size:0.88rem;">Condition keyword only</span>
        </div>
        <div style="background:var(--surface-2);border-radius:6px;padding:8px 12px;
                    font-family:monospace;font-size:0.82rem;color:var(--accent);
                    border:1px solid var(--border);margin-bottom:8px;">
          e.g. &quot;type 2 diabetes&quot;
        </div>
        <div style="color:var(--text-3);font-size:0.78rem;line-height:1.5;">
          Sent to <strong style="color:var(--text-2);">ClinicalTrials.gov</strong> — the US government's public
          clinical trial database. HTTPS encrypted. No authentication. No personal data attached.
        </div>
      </div>
      <!-- What is NOT sent -->
      <div style="border-top:1px solid var(--border);padding-top:14px;">
        <div style="font-size:0.75rem;font-weight:700;color:var(--text-3);
                    text-transform:uppercase;letter-spacing:0.08em;margin-bottom:10px;">
          Never included in that request:
        </div>
        <div style="display:flex;flex-direction:column;gap:6px;">
          <div style="display:flex;gap:8px;align-items:center;">
            <span style="color:var(--red);font-weight:700;font-size:0.8rem;">✗</span>
            <span style="color:var(--text-2);font-size:0.82rem;">Your name or identity</span>
          </div>
          <div style="display:flex;gap:8px;align-items:center;">
            <span style="color:var(--red);font-weight:700;font-size:0.8rem;">✗</span>
            <span style="color:var(--text-2);font-size:0.82rem;">Your age, sex, or diagnosis details</span>
          </div>
          <div style="display:flex;gap:8px;align-items:center;">
            <span style="color:var(--red);font-weight:700;font-size:0.8rem;">✗</span>
            <span style="color:var(--text-2);font-size:0.82rem;">Your medications or lab values</span>
          </div>
          <div style="display:flex;gap:8px;align-items:center;">
            <span style="color:var(--red);font-weight:700;font-size:0.8rem;">✗</span>
            <span style="color:var(--text-2);font-size:0.82rem;">Any AI outputs or match results</span>
          </div>
          <div style="display:flex;gap:8px;align-items:center;">
            <span style="color:var(--red);font-weight:700;font-size:0.8rem;">✗</span>
            <span style="color:var(--text-2);font-size:0.82rem;">Your PDF file or any part of it</span>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Architecture diagram -->
  <div style="background:var(--surface);border:1.5px solid var(--border);
              border-radius:14px;padding:24px;margin-bottom:28px;">
    <div style="font-weight:800;color:var(--text);font-size:0.88rem;
                text-transform:uppercase;letter-spacing:0.08em;margin-bottom:20px;">
      🏗️ Architecture — how data flows
    </div>
    <div style="display:flex;align-items:center;justify-content:center;
                flex-wrap:wrap;gap:8px;margin-bottom:20px;">

      <div style="background:var(--surface-2);border:1.5px solid var(--border-2);
                  border-radius:10px;padding:14px 18px;text-align:center;min-width:130px;">
        <div style="font-size:1.4rem;margin-bottom:6px;">📄</div>
        <div style="font-weight:700;color:var(--text);font-size:0.83rem;">Your PDF</div>
        <div style="color:var(--text-3);font-size:0.72rem;margin-top:3px;">Local file</div>
      </div>

      <div style="color:var(--text-3);font-size:1.4rem;font-weight:300;">→</div>

      <div style="background:var(--accent-bg);border:1.5px solid var(--accent);
                  border-radius:10px;padding:14px 18px;text-align:center;min-width:160px;">
        <div style="font-size:1.4rem;margin-bottom:6px;">🤖</div>
        <div style="font-weight:700;color:var(--accent);font-size:0.83rem;">Gemma 4 via Ollama</div>
        <div style="color:var(--text-3);font-size:0.72rem;margin-top:3px;">localhost:11434</div>
      </div>

      <div style="color:var(--text-3);font-size:1.4rem;font-weight:300;">→</div>

      <div style="background:var(--green-bg);border:1.5px solid var(--green-bd);
                  border-radius:10px;padding:14px 18px;text-align:center;min-width:130px;">
        <div style="font-size:1.4rem;margin-bottom:6px;">📊</div>
        <div style="font-weight:700;color:var(--green);font-size:0.83rem;">Results</div>
        <div style="color:var(--text-3);font-size:0.72rem;margin-top:3px;">Displayed locally</div>
      </div>
    </div>

    <!-- ClinicalTrials branch -->
    <div style="display:flex;align-items:center;justify-content:center;gap:8px;">
      <div style="width:1px;height:24px;background:var(--border-2);margin-left:calc(50% - 80px);"></div>
    </div>
    <div style="display:flex;justify-content:center;">
      <div style="background:var(--info-bg);border:1.5px solid var(--info-bd);
                  border-radius:10px;padding:12px 20px;text-align:center;max-width:300px;">
        <div style="font-size:1.1rem;margin-bottom:4px;">🔍</div>
        <div style="font-weight:700;color:var(--info);font-size:0.82rem;">ClinicalTrials.gov API</div>
        <div style="color:var(--text-3);font-size:0.72rem;margin-top:3px;">
          Keyword only · HTTPS · US gov public database
        </div>
      </div>
    </div>
    <div style="margin-top:14px;padding-top:14px;border-top:1px solid var(--border);
                color:var(--text-3);font-size:0.78rem;text-align:center;line-height:1.6;">
      Gemma 4 performs <strong style="color:var(--text-2);">three separate local inferences</strong>:
      extraction → clinical reasoning → eligibility matching.
      None of these calls leave your machine.
    </div>
  </div>

  <!-- Safety checklist -->
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:28px;">
    <div style="background:var(--surface);border:1.5px solid var(--border);border-radius:14px;padding:22px;">
      <div style="font-weight:800;color:var(--text);font-size:0.85rem;
                  margin-bottom:16px;text-transform:uppercase;letter-spacing:0.06em;">
        🛡️ Privacy guarantees
      </div>
      <div style="display:flex;flex-direction:column;gap:10px;">
        <div style="display:flex;gap:10px;align-items:flex-start;">
          <span style="color:var(--green);font-weight:800;flex-shrink:0;">✓</span>
          <span style="color:var(--text-2);font-size:0.85rem;">No account or sign-in required</span>
        </div>
        <div style="display:flex;gap:10px;align-items:flex-start;">
          <span style="color:var(--green);font-weight:800;flex-shrink:0;">✓</span>
          <span style="color:var(--text-2);font-size:0.85rem;">No data stored between sessions</span>
        </div>
        <div style="display:flex;gap:10px;align-items:flex-start;">
          <span style="color:var(--green);font-weight:800;flex-shrink:0;">✓</span>
          <span style="color:var(--text-2);font-size:0.85rem;">No analytics, telemetry, or logging</span>
        </div>
        <div style="display:flex;gap:10px;align-items:flex-start;">
          <span style="color:var(--green);font-weight:800;flex-shrink:0;">✓</span>
          <span style="color:var(--text-2);font-size:0.85rem;">No OpenAI, Anthropic, or any cloud AI</span>
        </div>
        <div style="display:flex;gap:10px;align-items:flex-start;">
          <span style="color:var(--green);font-weight:800;flex-shrink:0;">✓</span>
          <span style="color:var(--text-2);font-size:0.85rem;">Fully offline-capable (AI processing)</span>
        </div>
        <div style="display:flex;gap:10px;align-items:flex-start;">
          <span style="color:var(--green);font-weight:800;flex-shrink:0;">✓</span>
          <span style="color:var(--text-2);font-size:0.85rem;">Open source — every line is auditable</span>
        </div>
      </div>
    </div>

    <!-- Verify yourself -->
    <div style="background:var(--surface);border:1.5px solid var(--border);border-radius:14px;padding:22px;">
      <div style="font-weight:800;color:var(--text);font-size:0.85rem;
                  margin-bottom:16px;text-transform:uppercase;letter-spacing:0.06em;">
        🔎 Verify it yourself
      </div>
      <div style="color:var(--text-3);font-size:0.78rem;margin-bottom:12px;line-height:1.5;">
        Don't take our word for it. Watch the network traffic:
      </div>
      <div style="display:flex;flex-direction:column;gap:10px;">
        <div style="display:flex;gap:10px;align-items:flex-start;">
          <span style="background:var(--accent);color:#fff;border-radius:50%;
                       width:20px;height:20px;display:inline-flex;align-items:center;
                       justify-content:center;font-size:0.7rem;font-weight:700;flex-shrink:0;">1</span>
          <span style="color:var(--text-2);font-size:0.83rem;">Press <strong>F12</strong> to open DevTools → Network tab</span>
        </div>
        <div style="display:flex;gap:10px;align-items:flex-start;">
          <span style="background:var(--accent);color:#fff;border-radius:50%;
                       width:20px;height:20px;display:inline-flex;align-items:center;
                       justify-content:center;font-size:0.7rem;font-weight:700;flex-shrink:0;">2</span>
          <span style="color:var(--text-2);font-size:0.83rem;">Upload a PDF and run the analysis</span>
        </div>
        <div style="display:flex;gap:10px;align-items:flex-start;">
          <span style="background:var(--accent);color:#fff;border-radius:50%;
                       width:20px;height:20px;display:inline-flex;align-items:center;
                       justify-content:center;font-size:0.7rem;font-weight:700;flex-shrink:0;">3</span>
          <span style="color:var(--text-2);font-size:0.83rem;">You will see <strong>exactly one</strong> external request — to <code style="background:var(--surface-2);padding:1px 5px;border-radius:4px;font-size:0.78rem;">clinicaltrials.gov</code></span>
        </div>
        <div style="display:flex;gap:10px;align-items:flex-start;">
          <span style="background:var(--accent);color:#fff;border-radius:50%;
                       width:20px;height:20px;display:inline-flex;align-items:center;
                       justify-content:center;font-size:0.7rem;font-weight:700;flex-shrink:0;">4</span>
          <span style="color:var(--text-2);font-size:0.83rem;">Inspect its URL — it contains only your keyword, nothing else</span>
        </div>
      </div>
    </div>
  </div>

  <!-- Compliance note -->
  <div style="background:var(--amber-bg);border:1px solid var(--amber-bd);
              border-left:4px solid var(--amber);border-radius:10px;
              padding:16px 20px;margin-bottom:24px;
              display:flex;gap:14px;align-items:flex-start;">
    <span style="font-size:1.3rem;flex-shrink:0;">⚠️</span>
    <div>
      <div style="font-weight:700;color:var(--amber);font-size:0.85rem;margin-bottom:4px;">
        Designed for HIPAA-sensitive use cases
      </div>
      <div style="color:var(--text-2);font-size:0.82rem;line-height:1.6;">
        Because no protected health information (PHI) leaves the device, TrialMatch is suitable
        for deployment in clinical settings, research institutions, and privacy-regulated environments
        where cloud AI tools cannot be used.
        <strong style="color:var(--text);"> Always consult your institution's compliance team before use in a formal clinical workflow.</strong>
      </div>
    </div>
  </div>

  <!-- Track badge -->
  <div style="display:flex;justify-content:center;gap:12px;flex-wrap:wrap;">
    <div style="background:var(--surface-2);border:1px solid var(--border);
                border-radius:20px;padding:8px 18px;
                display:flex;align-items:center;gap:8px;">
      <span style="font-size:1rem;">🏆</span>
      <span style="font-weight:700;color:var(--text-2);font-size:0.8rem;">Safety &amp; Trust Track</span>
    </div>
    <div style="background:var(--surface-2);border:1px solid var(--border);
                border-radius:20px;padding:8px 18px;
                display:flex;align-items:center;gap:8px;">
      <span style="font-size:1rem;">🏆</span>
      <span style="font-weight:700;color:var(--text-2);font-size:0.8rem;">Health &amp; Sciences Track</span>
    </div>
    <div style="background:var(--surface-2);border:1px solid var(--border);
                border-radius:20px;padding:8px 18px;
                display:flex;align-items:center;gap:8px;">
      <span style="font-size:1rem;">🔒</span>
      <span style="font-weight:700;color:var(--text-2);font-size:0.8rem;">Gemma 4 Good Hackathon 2026</span>
    </div>
  </div>

</div>
"""

# ─────────────────────────────────────────────────────────────────────────────
# Gradio layout
# ─────────────────────────────────────────────────────────────────────────────

with gr.Blocks(title="TrialMatch") as demo:

    # Header contains the #tm-toggle button; _THEME_JS wires it via addEventListener
    gr.HTML(_HEADER_HTML)
    gr.HTML(_INFO_HTML)

    with gr.Tabs():

        with gr.Tab("🔬  Run Analysis"):
            gr.HTML("""
<div style="background:var(--surface);border:1px solid var(--border);
            border-left:4px solid var(--accent);border-radius:12px;
            padding:16px 22px;margin:0 0 20px;
            display:flex;align-items:center;gap:20px;font-family:system-ui,sans-serif;">
  <div style="text-align:center;flex-shrink:0;line-height:1;">
    <div style="font-size:2rem;font-weight:900;color:var(--accent);">400K</div>
    <div style="font-size:0.65rem;font-weight:700;color:var(--text-3);
                text-transform:uppercase;letter-spacing:0.08em;margin-top:3px;">patients / year</div>
  </div>
  <div>
    <div style="font-weight:700;color:var(--text);font-size:0.93rem;line-height:1.4;">
      400,000 patients miss qualifying trials every year.
    </div>
    <div style="color:var(--text-2);font-size:0.82rem;margin-top:4px;line-height:1.5;">
      TrialMatch finds yours in minutes &mdash; private, offline, no sign-up required.
    </div>
  </div>
</div>""")
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
                    gr.HTML(
                        f'<p style="font-size:0.76rem;color:var(--text-3);margin:-6px 0 10px;'
                        f'font-family:system-ui,sans-serif;">{_DB_INFO}</p>'
                    )
                    language_dropdown = gr.Dropdown(
                        choices=_LANGUAGES,
                        value="English",
                        label="Results Language",
                        info="Urdu and Arabic render right-to-left.",
                    )
                    gr.HTML(
                        '<div style="margin:-8px 0 12px;padding:10px 14px;'
                        'background:var(--accent-bg);border:1px solid var(--border-2);'
                        'border-left:3px solid var(--accent);border-radius:8px;'
                        'font-family:system-ui,sans-serif;">'
                        '<div style="font-size:0.81rem;color:var(--accent);font-weight:700;'
                        'margin-bottom:3px;">🌍 2 billion patients don\'t read English.</div>'
                        '<div style="font-size:0.78rem;color:var(--text-2);line-height:1.5;">'
                        'Results explained in your language — because healthcare information '
                        'should have no language barrier.</div>'
                        '</div>'
                    )
                    run_btn = gr.Button("▶  Run TrialMatch", variant="primary")
                    gr.HTML(
                        '<p style="font-size:0.76rem;color:var(--text-3);margin-top:6px;'
                        'text-align:center;font-family:system-ui,sans-serif;">'
                        'First run takes 2–3 min while the model loads</p>'
                    )
                    gr.HTML("""
<div style="margin-top:14px;border:1px solid var(--border);border-radius:10px;
            overflow:hidden;font-family:system-ui,sans-serif;font-size:0.77rem;">
  <div style="background:var(--surface-2);padding:7px 12px;border-bottom:1px solid var(--border);
              font-weight:700;color:var(--text-3);text-transform:uppercase;
              letter-spacing:0.07em;font-size:0.68rem;">🔒 Data flow</div>
  <div style="display:grid;grid-template-columns:1fr 1fr;">
    <div style="padding:10px 12px;border-right:1px solid var(--border);">
      <div style="color:var(--green);font-weight:700;margin-bottom:6px;">💻 Stays on device</div>
      <div style="color:var(--text-3);line-height:1.7;">
        PDF file<br>Medical profile<br>AI reasoning<br>Match results<br>Email drafts
      </div>
    </div>
    <div style="padding:10px 12px;">
      <div style="color:var(--info);font-weight:700;margin-bottom:6px;">🌐 Leaves device</div>
      <div style="color:var(--text-3);line-height:1.7;">
        Condition keyword only<br>
        <span style="font-size:0.72rem;">→ ClinicalTrials.gov (HTTPS)</span><br>
        <span style="color:var(--green);font-size:0.72rem;">No personal data. Ever.</span>
      </div>
    </div>
  </div>
</div>""")

                # ── Right: outputs ─────────────────────────────────────────────
                with gr.Column(scale=2, min_width=380):
                    status_box   = gr.HTML(value=_STATUS_PLACEHOLDER, elem_id="tm-status")
                    enrich_btn   = gr.Button(
                        "✨  Generate Reasoning & Emails",
                        variant="primary",
                        visible=True,
                        interactive=False,
                    )
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
                            'Select a language above then run the analysis. '
                            'Translation happens automatically. Urdu and Arabic render right-to-left. '
                            '10 languages: Urdu · Arabic · Hindi · Spanish · French · '
                            'Swahili · Chinese · Portuguese · Bengali.</p>'
                        )
                        translated_output = gr.HTML(value="")

            enrich_state = gr.State(value=None)

            run_btn.click(
                fn=run_trialmatch,
                inputs=[pdf_input, condition_input, language_dropdown],
                outputs=[status_box, results_html, email_box, translated_output, enrich_btn, enrich_state],
            )
            enrich_btn.click(
                fn=generate_enrichment,
                inputs=[enrich_state],
                outputs=[status_box, results_html, email_box, translated_output, enrich_btn],
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

        with gr.Tab("🔒  Privacy & Trust"):
            gr.HTML(_PRIVACY_HTML)

        with gr.Tab("⚙️  System Check"):
            gr.HTML(
                '<p style="font-family:system-ui,sans-serif;color:var(--text-2);'
                'font-size:0.88rem;margin-bottom:14px;">'
                'Verify that Ollama is running and '
                '<code style="background:var(--surface-2);padding:2px 6px;border-radius:4px;">'
                'gemma4:e4b</code> is installed before running the analysis.</p>'
            )
            with gr.Row():
                check_btn      = gr.Button("Check System", variant="secondary")
                speed_test_btn = gr.Button("Run Speed Test", variant="secondary")
            check_output = gr.HTML(
                value='<div style="color:var(--text-3);font-family:system-ui,sans-serif;'
                      'font-size:0.86rem;padding:8px 0;">Click Check System to begin…</div>'
            )
            check_btn.click(fn=check_system, inputs=[], outputs=[check_output])
            speed_test_btn.click(fn=run_speed_test, inputs=[], outputs=[check_output])

    gr.HTML(_DISCLAIMER_HTML)

    # Wire the #tm-toggle button and restore saved theme on every page load
    demo.load(fn=None, inputs=[], outputs=[], js=_THEME_JS)


if __name__ == "__main__":
    import socket
    from trial_fetcher import db_exists
    from download_trials_db import build_database

    # ── First-launch setup ────────────────────────────────────────────────────
    if not db_exists():
        print()
        print("Setting up TrialMatch for the first time...")
        print("(This downloads the offline trial database — takes 2-3 minutes, happens once only)")
        print()
        for line in build_database():
            print(line, flush=True)
        print()

    def _find_free_port(start=7860, end=7880):
        for port in range(start, end + 1):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(("127.0.0.1", port)) != 0:
                    return port
        return start

    port = _find_free_port()
    print(f"Starting TrialMatch — open http://127.0.0.1:{port} in your browser")
    demo.launch(
        server_name="0.0.0.0",
        server_port=port,
        share=False,
        inbrowser=False,
        theme=gr.themes.Soft(),
        css=_CSS,
        head=_HEAD_HTML,
    )
