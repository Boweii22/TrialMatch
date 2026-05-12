# TrialMatch — Setup Guide (Windows 11)

TrialMatch matches your medical records to open clinical trials using a local AI model.
**Nothing sensitive ever leaves your computer.**

---

## How It Works

1. **PDF reading** — Extracts text directly from text-based PDFs using PyMuPDF, and falls back to image conversion for scanned or image-based PDFs. Processes up to 2 pages.
2. **Profile extraction** — Gemma 4 reads the extracted text (or page images for scanned PDFs) and fills nine structured fields: Primary Diagnosis, Secondary Conditions, Current Medications, Patient Age, Patient Sex, Recent Lab Values, Recent Procedures, Allergies, and Exclusion Flags. Any field not found is recorded as NOT FOUND.
3. **Clinical reasoning** — Gemma 4 produces a structured four-line clinical summary: Clinical Severity, Disease Stability, Key Clinical Factors, and Potential Concerns. This contextualises the raw extracted data and improves matching accuracy.
4. **Trial fetch** — Queries the public ClinicalTrials.gov API for up to 5 recruiting trials matching the condition keyword, retrieving title, eligibility criteria, contact details, location, phase, sponsor, and estimated completion date.
5. **Matching** — For each trial, Gemma 4 returns a MATCH / PARTIAL / NO verdict with a confidence score (0–100), a plain-English reason, and instructs Gemma 4 to reference the specific eligibility criterion that caused a disqualification — output quality depends on model behaviour.
6. **Email draft** — For each MATCH verdict, generates a professional inquiry email pre-filled with the trial coordinator's contact details and a de-identified patient summary.
7. **Translation** — Translates the reason, next step, and disqualifier fields into Urdu, Arabic, or French, preserving English for all medical codes and drug names.

---

## Prerequisites

### 1. Install Python 3.10 or later
1. Go to https://python.org/downloads and click **Download Python 3.x.x**
2. Run the installer.  
   **Important:** On the first screen, tick the box **"Add Python to PATH"** before clicking Install Now.
3. Open a new Command Prompt and verify:
   ```
   python --version
   ```
   You should see `Python 3.10.x` or higher.

### 2. Install Ollama
1. Go to https://ollama.com and click **Download for Windows**
2. Run the installer (Ollama.exe). It installs a background service automatically.
3. Verify Ollama is running by opening a browser and going to:
   ```
   http://localhost:11434
   ```
   You should see the text `Ollama is running`.

### 3. Download the Gemma 4 model
Open **Command Prompt** and run:
```
ollama pull gemma4:e4b
```
This downloads the ~9.6 GB model file. Do this once; it is cached permanently.  
Wait for the download to complete before continuing.

---

## Installation

1. Open **Command Prompt** (`Win + R`, type `cmd`, press Enter)
2. Navigate to the TrialMatch folder:
   ```
   cd C:\Users\YourName\Downloads\TrialMatch
   ```
   *(replace `YourName` with your actual Windows username)*
3. Install the Python libraries:
   ```
   pip install -r requirements.txt
   ```
   Wait for all packages to install (takes 1–2 minutes on first run).

---

## Running the App

1. Make sure Ollama is running (the system tray icon, or run `ollama serve` in a terminal)
2. In Command Prompt, inside the TrialMatch folder:
   ```
   python app.py
   ```
3. Open your browser and go to:
   ```
   http://127.0.0.1:7860
   ```

---

## How to Use

1. **Make sure Ollama is running.** It starts automatically on Windows. If not, open it from the Start menu or run `ollama serve` in a terminal.
2. **Run the app.** In Command Prompt inside the TrialMatch folder: `python app.py`, then open `http://127.0.0.1:7860` in your browser.
3. **Run the System Check tab.** Click the ⚙️ System Check tab and press **Check System** — confirm Ollama is running and `gemma4:e4b` is found.
4. **Upload the patient PDF.** Switch to the Run Analysis tab and upload your PDF (e.g. `ahmed_raza_medical_record.pdf`) in Step 1.
5. **Type the condition.** In Step 2 enter a keyword such as `type 2 diabetes`.
6. **Click ▶ Run TrialMatch and wait.** On a CPU-only machine this takes **7–10 minutes**. Do not close the window — watch the status messages update as each step completes.
7. **Confirm results appear.** At least one MATCH or PARTIAL result should appear with a trial name, plain-English reason, and a next step.

---

## Troubleshooting

### "Cannot connect to Ollama"
- Make sure the Ollama application is open (look for it in the Windows system tray).
- If not running, open Command Prompt and type `ollama serve` then try again.

### "Model gemma4:e4b not found"
- Run `ollama pull gemma4:e4b` in Command Prompt and wait for the download to finish.
- The model is about 9.6 GB; check you have enough disk space.

### PDF read errors / blank profile
- Make sure the PDF is not password-protected or encrypted.
- Scanned PDFs (photos of pages) work best when the scan is clear and high-contrast.
- The app processes a maximum of 2 pages — ensure the relevant medical information is on the first 2 pages.

### No trials returned
- ClinicalTrials.gov requires an internet connection. Check you are online.
- Try a broader keyword: use `diabetes` instead of `type 2 diabetes`, or `cancer` instead of a specific subtype.
- Some rare conditions have very few open trials; try searching the ClinicalTrials.gov website directly.

### App is very slow
- This is normal on a CPU-only machine. The AI model is doing complex reasoning without a GPU.
- Close other applications to free RAM.
- The status box will update after each step so you know the app is working.

### "pip install" fails
- If an exact library version is not available on PyPI, edit `requirements.txt`, remove the `==X.Y.Z` pin from the failing line, and run `pip install -r requirements.txt` again.

### Browser shows a blank page or "connection refused"
- Make sure the Command Prompt window running `python app.py` is still open.
- The address must be `http://127.0.0.1:7860` (note: `http`, not `https`).

---

## Privacy Notes

- Your PDF is read locally by the AI model running on your own computer.
- The only data sent to the internet is the condition keyword you type (e.g. `diabetes`), sent to the public ClinicalTrials.gov API over HTTPS.
- No personal data, medical records, or AI responses are transmitted externally.

---

## Disclaimer

TrialMatch is a research and information tool. It does not provide medical advice, diagnosis, or treatment recommendations. Always consult a licensed physician before making any medical decisions or enrolling in a clinical trial.
