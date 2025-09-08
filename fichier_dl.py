from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import re
import os
import random
import requests
import logging
from datetime import datetime
from telegram_notifier import send_notification
from file_parser import parse_filename
from tqdm import tqdm

log = logging.getLogger(__name__)

class DownloadCancelledError(Exception):
    """Custom exception to indicate that a download was cancelled."""
    pass

class FichierDownloader:
    """Manages a persistent browser session to download files from 1fichier."""

    def __init__(self, download_dir=None, wait_time_minutes=10):
        self.download_dir = download_dir or os.path.join(os.getcwd(), "downloads")
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir)
        
        self.wait_time_seconds = wait_time_minutes * 60
        self.driver = None
        
        self.options = Options()
        self.options.add_argument("--headless=new")
        self.options.add_argument("--window-size=1920,1080")
        self.options.add_argument("--no-sandbox")
        self.options.add_argument("--disable-dev-shm-usage")

    def _save_error_debug_info(self):
        """Saves a screenshot and page source to a timestamped debug folder."""
        if not self.driver:
            return
        try:
            debug_dir = os.path.join(os.getcwd(), "debug_reports")
            if not os.path.exists(debug_dir):
                os.makedirs(debug_dir)
            
            timestamp = datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
            error_folder = os.path.join(debug_dir, f"error_{timestamp}")
            os.makedirs(error_folder)

            screenshot_path = os.path.join(error_folder, 'screenshot.png')
            self.driver.save_screenshot(screenshot_path)

            html_path = os.path.join(error_folder, 'page.html')
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(self.driver.page_source)
            
            log.info(f"Saved debug info to {error_folder}")
        except Exception as e:
            log.error(f"Failed to save debug info: {e}")

    def start_session(self):
        if not self.driver:
            log.info("Starting new browser session...")
            self.driver = webdriver.Chrome(options=self.options)

    def stop_session(self):
        if self.driver:
            log.info("Closing browser session...")
            self.driver.quit()
            self.driver = None

    def download_file(self, url, status_callback, cancellation_check=None):
        if not self.driver:
            raise Exception("Browser session not started. Call start_session() first.")

        try:
            if cancellation_check and cancellation_check():
                raise DownloadCancelledError()

            self.driver.get(url)

            try:
                cookie_button = WebDriverWait(self.driver, 5).until(EC.presence_of_element_located((By.CLASS_NAME, 'cmpboxbtnyes')))
                self.driver.execute_script("arguments[0].click();", cookie_button)
            except TimeoutException:
                pass

            page_text = self.driver.find_element(By.TAG_NAME, 'body').text

            if "Le fichier demandé n'existe pas" in page_text or "a été supprimé" in page_text:
                log.error("File does not exist or has been deleted.")
                status_callback("failed")
                return False

            if "vous devez attendre entre chaque téléchargement" in page_text:
                self._handle_wait_condition(status_callback, cancellation_check)
                # After waiting, retry the download for the same URL
                return self.download_file(url, status_callback, cancellation_check)

            # --- Page is valid, now we can set the status to processing ---
            status_callback("processing")
            log.info("Page seems valid, proceeding with download logic...")
            download_url = self._get_final_download_link(status_callback, cancellation_check)
            
            if download_url:
                self._download_from_link(download_url, status_callback, cancellation_check)
                status_callback("done", progress=100)
                return True
            else:
                log.error("Could not extract the final download link.")
                self._save_error_debug_info()
                status_callback("failed")
                return False
        
        except DownloadCancelledError:
            log.info("Download was cancelled by the user.")
            return False
        except Exception as e:
            log.error(f"An unexpected error occurred: {e}", exc_info=True)
            self._save_error_debug_info()
            status_callback("failed")
            return False

    def _handle_wait_condition(self, status_callback, cancellation_check):
        """Parses the wait time from the download button and waits accordingly."""
        status_callback("pending")
        # Set a default wait time in case parsing fails
        wait_seconds = self.wait_time_seconds 

        try:
            # Find the button with the countdown timer, which has id='dlw'
            timer_button = self.driver.find_element(By.ID, 'dlw')
            button_text = timer_button.text
            
            # Use regex to find the number of seconds in the button's text
            seconds_match = re.search(r'(\d+)', button_text)
            
            if seconds_match:
                parsed_seconds = int(seconds_match.group(1))
                if parsed_seconds > 0:
                    # Add a small buffer (e.g., 5 seconds) to account for script execution delays
                    wait_seconds = parsed_seconds + 5 
                    log.warning(f"Wait condition detected. Waiting for {wait_seconds} seconds based on page timer.")
                else:
                    log.warning(f"Parsed 0 or negative seconds from timer, using default wait.")
            else:
                log.warning(f"Could not parse seconds from button text: '{button_text}'. Falling back to default wait.")

        except Exception as e:
            log.error(f"Could not find or parse timer element (id='dlw'), falling back to default wait. Error: {e}")

        # Wait for the calculated duration, checking for cancellation every second
        wait_start_time = time.time()
        while time.time() - wait_start_time < wait_seconds:
            if cancellation_check and cancellation_check():
                raise DownloadCancelledError()
            time.sleep(1)
        log.info("Wait finished, proceeding to retry download.")


    def _get_final_download_link(self, status_callback, cancellation_check=None):
        try:
            wait_button = WebDriverWait(self.driver, 5).until(EC.presence_of_element_located((By.ID, 'dlw')))
            if not wait_button.is_enabled():
                log.info("Countdown detected. Setting status to PENDING.")
                status_callback("pending")
                
                # Wait for the button to be clickable, with cancellation checks
                wait_interval = 1 # seconds
                total_wait = 120 # seconds
                for _ in range(total_wait // wait_interval):
                    if cancellation_check and cancellation_check():
                        raise DownloadCancelledError()
                    try:
                        if WebDriverWait(self.driver, wait_interval).until(EC.element_to_be_clickable((By.ID, 'dlw'))):
                            break
                    except TimeoutException:
                        continue # Button not yet clickable, continue waiting
                else: # Loop finished without break
                    raise TimeoutException("Timed out waiting for download button to become clickable.")

            if cancellation_check and cancellation_check():
                raise DownloadCancelledError()

            log.info("Clicking button via JavaScript to avoid interception.")
            self.driver.execute_script("arguments[0].click();", wait_button)
        except TimeoutException:
            log.info("No initial wait button found.")

        try:
            download_button = WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.CLASS_NAME, 'ok')))
            return download_button.get_attribute('href')
        except TimeoutException:
            return None

    def _download_from_link(self, link, status_callback, cancellation_check=None):
        log.info("Starting file transfer...")
        try:
            with requests.get(link, stream=True, timeout=30) as r:
                r.raise_for_status()
                filename = "downloaded_file"
                if "content-disposition" in r.headers:
                    cd = r.headers['content-disposition']
                    fname_match = re.search('filename="(.+)"', cd)
                    if fname_match:
                        filename = fname_match.group(1)
                else:
                    filename = link.split('/')[-1]

                filepath = os.path.join(self.download_dir, filename)
                total_size = int(r.headers.get('content-length', 0))
                downloaded = 0
                last_reported_progress = -1

                status_callback("downloading", progress=0)
                with open(filepath, 'wb') as f, tqdm(
                    total=total_size,
                    unit='iB',
                    unit_scale=True,
                    desc=filename,
                    ncols=100
                ) as bar:
                    for chunk in r.iter_content(chunk_size=1048576):
                        if cancellation_check and cancellation_check():
                            raise DownloadCancelledError()
                        
                        f.write(chunk)
                        downloaded += len(chunk)
                        bar.update(len(chunk))
                        progress = (downloaded / total_size) * 100 if total_size > 0 else 0
                        
                        if progress >= last_reported_progress + 0.1:
                            status_callback("downloading", progress=round(progress, 2))
                            last_reported_progress = progress
            
            status_callback("done", progress=100)
            log.info(f"File downloaded successfully to {filename}")

            media_info = parse_filename(filename)
            title = media_info.get('title', filename)
            media_type = media_info.get('type', 'file')

            if media_type == 'tv_show':
                media_type = 'TV show'
                title = f"{title} S{media_info.get('season', '')}E{media_info.get('episode', '')}"

            messages = [
                f"Hey! Your {media_type} '{title}' is ready. Grab some popcorn! 🍿",
                f"Success! '{title}' has finished downloading. Hope you enjoy it! 🎬",
                f"Good news! Your {media_type} '{title}' has arrived. Time for a movie night! ✨",
                f"Voilà! '{title}' is downloaded and waiting for you. 🎉",
                f"Mission accomplished. Your {media_type} '{title}' is now in your collection. 🚀",
                f"Beep boop... Download complete! '{title}' is ready for viewing. 🤖",
                f"The eagle has landed. I repeat, '{title}' has landed. 🦅",
                f"It's here! '{title}' has been successfully retrieved from the digital cosmos. 🌌",
                f"Your download of '{title}' is complete. Let the binge-watching commence! 📺",
                f"I've got your {media_type}! '{title}' is downloaded and ready to roll. 🎞️"
            ]
            
            send_notification(random.choice(messages))

        except requests.exceptions.RequestException as e:
            log.error(f"An error occurred during download: {e}")
            raise

def get_filename_from_url(url):
    """Uses a temporary Selenium session to get the filename from a 1fichier URL."""
    log.info(f"Using Selenium to get filename from {url}")
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        driver.get(url)

        try:
            cookie_button = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CLASS_NAME, 'cmpboxbtnyes')))
            driver.execute_script("arguments[0].click();", cookie_button)
            log.info("Clicked the cookie consent button.")
        except TimeoutException:
            log.info("Cookie consent button not found, proceeding anyway.")

        selector = 'form table.premium td.normal span[style*="font-weight:bold"]'
                
        wait = WebDriverWait(driver, 10)
        filename_element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
        
        filename = filename_element.text
        log.info(f"Successfully extracted filename: {filename}")
        return filename
    except TimeoutException:
        log.error(f"Timed out waiting for filename element with selector: {selector}")
        return None
    except Exception as e:
        log.error(f"An unexpected error occurred in get_filename_from_url: {e}", exc_info=True)
        return None
    finally:
        if driver:
            driver.quit()