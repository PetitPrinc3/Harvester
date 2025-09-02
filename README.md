# Harvester

> VibeCoded by Gemini CLI with :heart:

Harvester is an automated service designed to integrate with media servers like Jellyseer. It processes movie or TV show requests by finding the best available version from web sources, handling download links, and downloading the media.

## Features

- **Dynamic URL Retrieval**: Automatically fetches the latest website address from a specified Telegram channel.
- **Intelligent Media Search**: Searches for movies and TV shows and parses the results across all available pages.
- **Advanced Scoring & Selection**: 
    - Uses fuzzy matching to handle typos and variations in titles.
    - Applies a detailed, customizable scoring system for language, quality, and link completeness to select the best possible version.
    - Verifies that a chosen result has a valid `1fichier` download link before proceeding.
- **Manual Captcha Handling**: Provides a simple command-line interface for the user to solve `dl-protect` captchas and provide the final download links.
- **Robust Downloader**: 
    - Downloads files from `1fichier` links.
    - Automatically handles "wait time" errors by waiting and retrying, ensuring resilience.
    - Fails gracefully if a file is confirmed to be deleted or missing.

## Project Structure

- `harvester.py`: The main entry point and orchestrator for the entire workflow.
- `telegram_parser.py`: A module to connect to Telegram and find the source website URL.
- `zt_parser.py`: A powerful parser and media selector for Zone-Telechargement.
- `fichier_dl.py`: A robust, resilient downloader for `1fichier` links.
- `requirements.txt`: A list of all necessary Python libraries.
- `.env`: Configuration file for storing API keys and other secrets.
- `.gitignore`: Ensures that secrets and session files are not committed to version control.

## Setup & Installation

1.  **Clone the repository (optional):**
    ```bash
    git clone <repository_url>
    ```

2.  **Install Dependencies:**
    Make sure you have Python 3 installed, then run:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configure Environment:**
    - Rename the `.env.example` file (if provided) to `.env` or create a new `.env` file.
    - Add your Telegram API credentials to the `.env` file:
      ```
      TELEGRAM_API_ID=your_api_id
      TELEGRAM_API_HASH=your_api_hash
      ```

4.  **First-time Telegram Login:**
    The first time you run the script, Telethon will need to create a session file. You will be prompted in the terminal to enter your phone number, the login code sent to you by Telegram, and your 2FA password (if applicable).

## Usage

To run the service, execute the main harvester script from your terminal:

```bash
python harvester.py
```

The script will then execute the full workflow:
1.  Fetch the ZT URL from Telegram.
2.  Search for the media defined in the hardcoded request within `harvester.py`.
3.  Select the best version and present you with the `dl-protect` links.
4.  Wait for you to solve the captchas and paste the final `1fichier` links back into the terminal.
5.  Download all files sequentially into the `downloads` folder.