# Harvester

Harvester is a self-hosted download manager for `1fichier.com`, designed for seamless, unattended operation. It features a modern web interface, a powerful Telegram bot for link submission, and a resilient download queue that automatically handles wait times and retries.

![Harvester Queue UI](https://i.imgur.com/example.png) *(Image placeholder: A screenshot of the web UI's queue page would be ideal here)*

## Key Features

-   **Web UI**: A clean, responsive web interface to submit links and manage the download queue.
-   **Dynamic Download Queue**: View real-time status, progress, and metadata for all files. Interactively reorder the queue priority, delete items, and monitor activity.
-   **Telegram Bot Integration**: Add new downloads simply by sending `1fichier.com` links to your configured Telegram bot. The bot provides feedback on which links were successfully added or why they failed.
-   **Automated Download Handling**: Harvester uses a Selenium backend to intelligently navigate `1fichier.com`, automatically waiting for timers to expire before starting the download.
-   **Resilient & Persistent**: The application uses an SQLite database to maintain the queue's state. It automatically resumes any in-progress downloads on restart and retries failed downloads once.
-   **Console Monitoring**: See detailed logs and a live `tqdm` progress bar for the currently active download directly in your console.
-   **Completion Notifications**: Receive a notification via Telegram as soon as a file has finished downloading.
-   **Containerized**: The entire application is containerized with Docker for a simple, one-command setup and consistent deployment.

## Setup & Installation

### Prerequisites

-   [Docker](https://www.docker.com/get-started) installed on your system.
-   A Telegram account to create a bot and get API credentials.

### 1. Configuration

Before running the application, you need to provide your Telegram API credentials.

1.  **Create a Telegram Bot**:
    -   Talk to the [@BotFather](https://t.me/BotFather) on Telegram.
    -   Create a new bot to get your **Bot Token**.
    -   Create a new app at [my.telegram.org](https://my.telegram.org) to get your **API ID** and **API Hash**.

2.  **Get your Chat ID**:
    -   Create a new private group on Telegram and add your bot to it.
    -   Send a message to the group.
    -   Forward that message to the [@userinfobot](https://t.me/userinfobot) to get the group's **Chat ID** (it will be a negative number, like `-100123456789`).

3.  **Create the `.env` file**:
    In the root of the project directory, create a file named `.env` and add your credentials to it.

    ```env
    # Telegram API Credentials
    TELEGRAM_API_ID=1234567
    TELEGRAM_API_HASH=your_api_hash_here
    TELEGRAM_BOT_TOKEN=your_bot_token_here
    TELEGRAM_GROUP_CHAT_ID=-100123456789

    # Optional: Specify a filename for the log file
    LOG_FILENAME=harvester.log
    ```

### 2. Running with Docker

This is the recommended method for running Harvester.

1.  **Build the Docker Image**:
    ```sh
    docker build -t harvester .
    ```

2.  **Run the Docker Container**:
    This command will start the server, map the necessary ports and volumes, and ensure it restarts automatically.

    ```sh
    docker run -d \
      -p 5000:5000 \
      -v ./downloads:/app/downloads \
      -v ./harvester.db:/app/harvester.db \
      --env-file .env \
      --name harvester-app \
      --restart=unless-stopped \
      harvester
    ```
    -   `-d`: Run the container in detached mode.
    -   `-p 5000:5000`: Maps the container's port 5000 to your host's port 5000.
    -   `-v ./downloads:/app/downloads`: Mounts a local `downloads` folder to store completed files.
    -   `-v ./harvester.db:/app/harvester.db`: Mounts the SQLite database file locally for persistence.
    -   `--env-file .env`: Loads the environment variables from your `.env` file.
    -   `--name harvester-app`: Assigns a convenient name to the container.
    -   `--restart=unless-stopped`: Ensures the container automatically restarts on boot or if it crashes.

## Usage

1.  **Access the Web UI**:
    Open your web browser and navigate to `http://localhost:5000`. From here, you can submit links and view the download queue.

2.  **Use the Telegram Bot**:
    Simply send a message containing one or more `1fichier.com` links to the Telegram group you created. The bot will process them and add them to the queue.

3.  **View Logs**:
    To see the live logs and the download progress bar, you can tail the container's logs:
    ```sh
    docker logs -f harvester-app
    ```

---

<p align="center">
  Vibe-coded with ❤️ by Google Gemini - CLI
</p>
