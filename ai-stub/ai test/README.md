# Gemini API Test Stub

A minimal Python application for testing a prompt against Google's Gemini API. The application reads the prompt from `prompt.txt`, sends it to the Gemini model configured in `.env`, and prints the generated response in the terminal.

This is a **command-line test stub**, not a web server or an HTTP API endpoint.

## Project files

| File | Purpose |
| --- | --- |
| `main.py` | Entry point: calls `run_gemini()` and prints the response. |
| `readprompt.py` | Loads configuration, reads the prompt, sends the Gemini request, and retries certain server errors. |
| `prompt.txt` | The text sent to Gemini. Edit this file to change the prompt. |
| `requirements.txt` | Python packages required by the application. |
| `.env.example` | Template for local configuration; copy it to `.env`. |
| `.env` | Local API key and model configuration. **Never commit this file.** |
| `promptlog.txt` | Currently unused; the stub does **not** write responses to this file. |

## Requirements

- Python 3.14 (the stub was developed with Python 3.14.7).
- Internet access.
- A valid Gemini API key from [Google AI Studio](https://aistudio.google.com/api-keys), with access to the selected model.

## Getting started

Open a terminal in the folder containing `main.py`.

### 1. Create a virtual environment (recommended)

On Windows with PowerShell:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, you can use `.\.venv\Scripts\python.exe` instead of `python` in the commands below without activating the environment.

### 2. Install the dependencies

```powershell
python -m pip install -r requirements.txt
```

The two direct dependencies used by this project are `google-genai` and `python-dotenv`. The included `requirements.txt` pins their versions and the versions of their transitive dependencies.

### 3. Configure the API key and model

Create a file named `.env` in the project folder. You can copy `.env.example` and replace the placeholder values:

```dotenv
GEMINI_API_KEY=YOUR_OWN_API_KEY
GEMINI_MODEL=YOUR_AVAILABLE_MODEL_ID
```

- `GEMINI_API_KEY`: your personal API key from Google AI Studio.
- `GEMINI_MODEL`: the exact Gemini model ID your key can access (for example, the model your team has selected).

No quotation marks are required. **Do not add `.env` to Git.**

### 4. Edit the prompt

Open `prompt.txt` and replace its contents with the instruction you want to send to Gemini. The current stub sends the entire file as **one prompt** for **one API request**.

### 5. Run the application

```powershell
python main.py
```

The generated text appears in the terminal, preceded by:

```text
--- Response from Gemini ---
```

## How it works

```text
python main.py
    |
    v
main.py calls run_gemini()
    |
    v
readprompt.py loads .env and reads prompt.txt
    |
    v
Google Gemini API (model specified in GEMINI_MODEL)
    |
    v
Response text returned to main.py and printed
```

The function `run_gemini()` returns the generated text, so it can also be imported by another Python module:

```python
from readprompt import run_gemini

result = run_gemini()
print(result)
```

`generate_with_retry()` handles HTTP **503** server-unavailable errors by retrying up to five attempts, waiting 1, 2, 4, and 8 seconds between attempts. Other errors are raised instead of being silently ignored. The Google client may also perform its own retries.

## Troubleshooting

| Error | What to check |
| --- | --- |
| `ModuleNotFoundError: No module named 'dotenv'` or `'google'` | Install requirements using the Python interpreter running the script. |
| `KeyError: 'GEMINI_API_KEY'` | `.env` is missing or the API key variable is not present. |
| `KeyError: 'GEMINI_MODEL'` | Add `GEMINI_MODEL=...` to `.env`. |
| Model not found / model unavailable | Confirm the model ID exists and is accessible with your API key. |
| `503 UNAVAILABLE` | Gemini is temporarily unavailable or overloaded. The script retries automatically, but repeated failures can still occur. |
| `FileNotFoundError` for `prompt.txt` | Make sure `prompt.txt` is next to `readprompt.py`. |

## Git and security

Keep at least these entries in `.gitignore`:

```gitignore
.env
.venv/
__pycache__/
*.pyc
```

Only share `.env.example`, never a working `.env`. Each team member should configure their own authorized API key. If a real key has been shared publicly or committed to Git, **revoke it and create a new one**; simply deleting it from the latest commit does not remove it from Git history.

## Current limitations / next steps

- Only one prompt file (`prompt.txt`) and one request per run.
- Response is printed to the terminal; it is **not** saved to `promptlog.txt`.
- The program does not expose an API endpoint or user interface.
- Errors other than 503 are not handled with user-friendly messages yet.

These can be extended when the stub is integrated into the larger IT project.
