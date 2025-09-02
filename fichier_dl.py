from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import re
import os
import requests
import logging

log = logging.getLogger(__name__)

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

    def start_session(self):
        if not self.driver:
            log.info("Starting new browser session...")
            self.driver = webdriver.Chrome(options=self.options)

    def stop_session(self):
        if self.driver:
            log.info("Closing browser session...")
            self.driver.quit()
            self.driver = None

    def download_file(self, url, status_callback):
        if not self.driver:
            raise Exception("Browser session not started. Call start_session() first.")

        try:
            while True:
                log.info(f"Navigating to {url}")
                self.driver.get(url)

                try:
                    WebDriverWait(self.driver, 5).until(EC.presence_of_element_located((By.CLASS_NAME, 'cmpboxbtnyes'))).click()
                except TimeoutException:
                    pass

                page_text = self.driver.find_element(By.TAG_NAME, 'body').text

                if "Le fichier demandé n'existe pas" in page_text or "a été supprimé" in page_text:
                    log.error("File does not exist or has been deleted.")
                    status_callback("failed")
                    return False

                if "vous devez attendre entre chaque téléchargement" in page_text:
                    log.warning(f"Wait condition detected. Waiting for {self.wait_time_seconds / 60} minutes...")
                    status_callback("pending")
                    time.sleep(self.wait_time_seconds)
                    continue

                log.info("Page seems valid, proceeding with download logic...")
                download_url = self._get_final_download_link(status_callback)
                
                if download_url:
                    self._download_from_link(download_url, status_callback)
                    status_callback("done", progress=100) # Ensure final status is 100%
                    return True
                else:
                    log.error("Could not extract the final download link.")
                    status_callback("failed")
                    return False

        except Exception as e:
            log.error(f"An unexpected error occurred: {e}", exc_info=True)
            status_callback("failed")
            return False

    def _get_final_download_link(self, status_callback):
        try:
            wait_button = WebDriverWait(self.driver, 5).until(EC.presence_of_element_located((By.ID, 'dlw')))
            if not wait_button.is_enabled():
                log.info("Countdown detected. Setting status to PENDING.")
                status_callback("pending")
                WebDriverWait(self.driver, 120).until(EC.element_to_be_clickable((By.ID, 'dlw')))
            
            log.info("Clicking button via JavaScript to avoid interception.")
            self.driver.execute_script("arguments[0].click();", wait_button)
        except TimeoutException:
            log.info("No initial wait button found.")

        try:
            download_button = WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.CLASS_NAME, 'ok')))
            return download_button.get_attribute('href')
        except TimeoutException:
            return None

    def _download_from_link(self, link, status_callback):
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
                with open(filepath, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                        downloaded += len(chunk)
                        progress = (downloaded / total_size) * 100 if total_size > 0 else 0
                        
                        if progress >= last_reported_progress + 0.1:
                            status_callback("downloading", progress=round(progress, 2))
                            last_reported_progress = progress
            
            # Ensure progress is marked as 100% after successful download
            status_callback("downloading", progress=100)
            log.info(f"File downloaded successfully to {filepath}")
        except requests.exceptions.RequestException as e:
            log.error(f"An error occurred during download: {e}")
            raise
