# This script requires 'requests' and 'tqdm'. Please install them using: pip install requests tqdm

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import re
import sys
import os
import requests
from tqdm import tqdm

class FichierDownloader:
    """A robust downloader for 1fichier links."""

    def __init__(self, download_dir=None, wait_time_minutes=10):
        self.download_dir = download_dir or os.path.join(os.getcwd(), "downloads")
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir)
        self.wait_time_seconds = wait_time_minutes * 60

    def download_file(self, url):
        """
        Downloads a file from a given 1fichier URL with retries for wait pages.
        Returns True on success, False on failure.
        """
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")
        driver = webdriver.Chrome(options=options)
        
        try:
            while True:
                print(f"Navigating to {url}")
                driver.get(url)

                # Handle cookie consent first
                try:
                    cookie_button = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CLASS_NAME, 'cmpboxbtnyes')))
                    driver.execute_script("arguments[0].click();", cookie_button)
                    print("Cookie consent clicked.")
                except TimeoutException:
                    print("Cookie consent banner not found.")

                page_text = driver.find_element(By.TAG_NAME, 'body').text

                # Check for fatal errors
                if "Le fichier demandé n'existe pas" in page_text or "a été supprimé" in page_text:
                    print("Error: File does not exist or has been deleted.")
                    return False

                # Check for wait condition
                if "vous devez attendre entre chaque téléchargement" in page_text:
                    print(f"Wait condition detected. Waiting for {self.wait_time_seconds / 60} minutes before retrying...")
                    time.sleep(self.wait_time_seconds)
                    continue # Retry the URL

                # --- If no errors, proceed with download ---
                print("Page seems valid, proceeding with download logic...")
                download_url = self._get_final_download_link(driver)
                if download_url:
                    self._download_from_link(download_url)
                    return True
                else:
                    print("Could not extract the final download link.")
                    return False

        except Exception as e:
            print(f"An unexpected error occurred during the download process: {e}")
            return False
        finally:
            driver.quit()

    def _get_final_download_link(self, driver):
        """Extracts the final download link from a 1fichier page."""
        try:
            wait_button = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.ID, 'dlw')))
            print("Wait button found. Waiting for it to become clickable...")
            WebDriverWait(driver, 120).until(EC.element_to_be_clickable((By.ID, 'dlw')))
            print("Countdown finished. Clicking button via JavaScript to avoid interception.")
            driver.execute_script("arguments[0].click();", wait_button)
        except TimeoutException:
            print("No initial wait button found. Looking for download button directly.")

        try:
            download_button = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CLASS_NAME, 'ok')))
            final_link = download_button.get_attribute('href')
            print(f"Download link found: {final_link}")
            return final_link
        except TimeoutException:
            return None

    def _download_from_link(self, link):
        """Downloads a file from a direct URL using requests."""
        print("Starting file download...")
        try:
            with requests.get(link, stream=True) as r:
                r.raise_for_status()
                filename = "downloaded_file" # Fallback
                if "content-disposition" in r.headers:
                    cd = r.headers['content-disposition']
                    fname_match = re.search('filename="(.+)"', cd)
                    if fname_match:
                        filename = fname_match.group(1)
                else:
                    filename = link.split('/')[-1]

                filepath = os.path.join(self.download_dir, filename)
                total_size = int(r.headers.get('content-length', 0))

                with open(filepath, 'wb') as f, tqdm(
                    desc=filename,
                    total=total_size,
                    unit='iB',
                    unit_scale=True,
                    unit_divisor=1024,
                ) as bar:
                    for chunk in r.iter_content(chunk_size=8192):
                        size = f.write(chunk)
                        bar.update(size)
            print(f"\nFile downloaded successfully to {filepath}")
        except requests.exceptions.RequestException as e:
            print(f"\nAn error occurred during download: {e}")
