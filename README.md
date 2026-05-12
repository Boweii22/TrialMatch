# TrialMatch — Setup Guide (Windows 11)

TrialMatch matches your medical records to open clinical trials using a local AI model.
**Nothing sensitive ever leaves your computer.**

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

1. Click the **System Check** tab first to confirm Ollama and the model are ready.
2. Switch to the **Run Analysis** tab.
3. Upload your medical records PDF using **Step 1**.
4. Type your primary condition keyword in **Step 2** (e.g. `type 2 diabetes`).
5. Click **▶ Run TrialMatch**.
6. Watch the status box — the AI will read your records, search for trials, and match each one.  
   **First run may take 7–10 minutes** on a CPU-only machine while the model processes each step. Subsequent runs are faster once the model is loaded.
7. Results show each matching trial with a verdict, plain-English reason, and a next step.

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
