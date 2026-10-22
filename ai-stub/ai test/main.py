from readprompt import run_gemini

def main():
    response = run_gemini()
    print("--- Response from Gemini ---")
    print(response)

if __name__ == "__main__":
    main()