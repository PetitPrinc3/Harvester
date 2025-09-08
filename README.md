# Harvester

## Overview

Harvester is a web-based application designed to streamline downloading files from `1fichier.com`. It provides a modern web interface to submit links, automatically parses filenames to identify media, and manages the entire download process in a persistent queue.

The application is fully containerized with Docker for easy setup and deployment.

## Features

- **Web UI for Link Submission**: A simple page to submit one or more `1fichier.com` links.
- **Smart Metadata Parsing**: Automatically identifies media type (Movie or TV Show), title, year, season, and episode by querying The Movie Database (TMDB) API.
- **Dynamic Download Queue**: A queue viewer page that displays the status of all downloads in real-time.
- **Queue Management**: Interactively reorder the download queue priority, delete items, and filter the view by status or media type.
- **Resilient Downloading**: Automatically resumes any in-progress downloads on application restart and retries failed downloads once.
- **Production Ready**: Runs on a production-grade WSGI server (`waitress`) with intelligent logging.
- **Containerized**: Fully self-contained in a single Docker image.

## Requirements

- [Docker](https://www.docker.com/get-started)
- A [TMDB (The Movie Database)](https://www.themoviedb.org/signup) account and API Key.

## Setup

1.  **Create Environment File**: In the project root, create a file named `.env`.

2.  **Add API Key**: Add your TMDB API Key to the `.env` file like so:
    ```
    TMDB_API_KEY=your_tmdb_api_key_here
    ```

3.  **Build the Docker Image**: Open a terminal in the project root and run the build command:
    ```sh
    docker build -t harvester .
    ```

4.  **Run the Docker Container**: Run the application with the following command. This will start the server, mount your local project directory for instant code changes, and pass in your API key.
    ```sh
    docker run -p 5000:5000 -v ".:/app" -v /app/venv --env-file .env --name harvester-app harvester
    ```
    *Note: The `-v /app/venv` part is important as it prevents your local Python virtual environment from conflicting with the container's environment.*

## Usage

1.  **Access the Web UI**: Open your web browser and navigate to `http://localhost:5000`.

2.  **Submit Links**: Paste your `1fichier.com` links into the text area and click "Submit".

3.  **Manage Queue**: Navigate to the "Download Queue" page to view progress, reorder items, and manage your downloads.

---

<p align="center">
  Built with ❤️ by Google Gemini - CLI
</p>