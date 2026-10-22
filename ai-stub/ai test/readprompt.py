
import os
import time
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import errors

# Load API key from .env
load_dotenv(Path(__file__).parent / ".env")

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
aimodel = os.environ["GEMINI_MODEL"]

def generate_with_retry(prompt, max_attempts=5):
    for attempt in range(max_attempts):
        try:
            response = client.models.generate_content(
                model=aimodel,
                contents=prompt
            )
            return response.text

        except errors.ServerError as e:
            if e.code != 503 or attempt == max_attempts - 1:
                raise

            wait = 2 ** attempt
            print(f"Server busy. Retrying in {wait} seconds...")
            time.sleep(wait)


def run_gemini():
    # Read prompt from file
    prompt_path = Path(__file__).parent / "prompt.txt"
    prompt = prompt_path.read_text(encoding="utf-8").strip()

    # Generate and return response
    return generate_with_retry(prompt)
