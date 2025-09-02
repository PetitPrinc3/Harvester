# Harvester

> VibeCoded by Gemini CLI with :heart:

Harvester is an automated service designed to integrate with media servers like Jellyseer. It processes movie or TV show requests by finding the best available version from web sources, handling download links, and downloading the media in the background.

## Features

- **API Driven**: A Flask-based web service provides endpoints for requesting media, submitting solved links, and checking status.
- **Containerized**: The entire application is packaged in a Docker container for easy deployment and portability.
- **Persistent State**: Uses an SQLite database to track the status of all requests and downloads, ensuring data survives restarts.
- **Background Job Processing**: Features a multi-threaded architecture with a download queue to handle long-running tasks without blocking the API.
- **Dynamic URL Retrieval**: Automatically fetches the latest website address from a specified Telegram channel.
- **Intelligent Media Search**: Searches for movies and TV shows and parses the results across all available pages.
- **Advanced Scoring & Selection**: 
    - Uses fuzzy matching to handle typos and variations in titles.
    - Applies a detailed, customizable scoring system for language, quality, and link completeness to select the best possible version.
    - Verifies that a chosen result has a valid `1fichier` download link before proceeding.
- **Robust Downloader**: 
    - Downloads files from `1fichier` links using a persistent browser session to prevent errors.
    - Automatically handles "wait time" errors by waiting and retrying.
- **Smart Logging**: All application events are logged to both the console and a configurable log file (`journal.log` by default).

## Project Structure

- `Dockerfile`: Defines the container for the application.
- `app.py`: The main Flask application, containing the API endpoints and background workers.
- `database.py`: Manages the SQLite database schema and all data interactions.
- `logger_setup.py`: Configures the application-wide logging.
- `setup.py`: A one-time interactive script to handle Telegram login.
- `telegram_parser.py`: Module to connect to Telegram and find the source website URL.
- `zt_parser.py`: The powerful parser and media selector.
- `fichier_dl.py`: The robust, resilient downloader for `1fichier` links.
- `requirements.txt`: A list of all necessary Python libraries.
- `.env`: Configuration file for storing API keys and other secrets.

## Setup & Usage

The application is designed to run inside Docker. You only need Docker installed on your host machine.

### Step 1: Build the Docker Image

From the project root directory, build the image:
```bash
docker build -t harvester-service .
```

### Step 2: One-Time Telegram Setup

Run the interactive setup script inside a temporary container. This will prompt you for your Telegram credentials to create a session file. This file will be saved to your project directory.

```bash
docker run -it --rm -v ".:/app" harvester-service python setup.py
```

### Step 3: Run the Application

Once the setup is complete, run the main application server. The volume mount (`-v`) is crucial as it ensures that the database and log files are saved on your host machine.

```bash
docker run --rm -p 5000:5000 -v ".:/app" --name harvester-app harvester-service
```

The Harvester API will now be running on `http://localhost:5000`.

## API Endpoints

- `POST /request`
  - Submits a new media request. The background process of finding the media will begin.
  - **Body**:
    ```json
    {"type": "tv_show", "title": "Mr. Robot", "season": 1}
    ```
  - **Returns**: A `request_id` for tracking.

- `GET /status/<request_id>`
  - Checks the progress of a request. Once the search is complete, this will return the `dl-protect` links that need to be solved.

- `POST /submit`
  - Submits the final `1fichier` links after solving the captchas. This will queue the files for download.
  - **Body**:
    ```json
    {
        "downloads": [
            { "id": 1, "fichier_link": "https://1fichier.com/?..." },
            { "id": 2, "fichier_link": "https://1fichier.com/?..." }
        ]
    }
    ```
