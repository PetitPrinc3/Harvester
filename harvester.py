import json
from telegram_parser import TelegramParser
from zt_parser import ZTParser, select_best_movie, select_best_show
from fichier_dl import FichierDownloader

def main():
    """Main orchestrator for the Harvester service."""

    # --- 1. Define the Jellyseer Request ---
    # For this example, we'll use a hardcoded request.
    # In a real application, this would come from Jellyseer's API.
    request = {
        "type": "tv_show", # or "movie"
        "title": "Murder",
        "season": 6
    }
    # request = {
    #     "type": "movie",
    #     "title": "Matrix Reloaded"
    # }
    print(f"--- Starting Harvester for request: {request['title']} ---")

    # --- 2. Get ZT Address from Telegram ---
    print("\n--- Step 1: Fetching website URL from Telegram ---")
    tg_parser = TelegramParser()
    base_url = tg_parser.find_latest_zt_link()
    if not base_url:
        print("Could not retrieve website URL. Aborting.")
        return
    print(f"Using base URL: {base_url}")

    # --- 3. Search and Select Best Media ---
    print("\n--- Step 2: Searching for media and selecting best match ---")
    zt_parser = ZTParser(base_url=base_url)
    search_results = zt_parser.search(request['title'], 'series' if request['type'] == 'tv_show' else 'films')
    
    best_media = None
    if request['type'] == 'tv_show':
        best_media = select_best_show(zt_parser, search_results, request['title'], request['season'])
    else:
        best_media = select_best_movie(zt_parser, search_results, request['title'])

    if not best_media:
        print("Could not find a suitable media version. Aborting.")
        return
    
    print("\n--- Best Match Found ---")
    print(json.dumps(best_media, indent=4))

    # --- 4. Manual Captcha Exchange ---
    print("\n--- Step 3: Manual Captcha Solving ---")
    dl_protect_links = []
    if request['type'] == 'movie':
        dl_protect_links.append(best_media['dl_protect_link'])
    else: # TV Show
        for episode in best_media['episode_data']:
            dl_protect_links.append(episode['dl_protect_link'])

    fichier_links = []
    for i, link in enumerate(dl_protect_links):
        print(f"\nACTION REQUIRED for episode {i+1}/{len(dl_protect_links)}:")
        print(f"1. Open this URL in your browser: {link}")
        print("2. Solve the captcha and click the button.")
        print("3. You will be redirected to a 1fichier.com page.")
        fichier_url = input("4. Paste the final 1fichier.com URL here and press Enter: ")
        if "1fichier.com" in fichier_url:
            fichier_links.append(fichier_url.strip())
        else:
            print("Invalid URL. Skipping this link.")

    # --- 5. Download Final Files ---
    print(f"\n--- Step 4: Downloading {len(fichier_links)} file(s) ---")
    downloader = FichierDownloader()
    for i, link in enumerate(fichier_links):
        print(f"\nDownloading file {i+1}/{len(fichier_links)}...")
        success = downloader.download_file(link)
        if not success:
            print(f"Failed to download {link}. Moving to next file.")

    print("\n--- Harvester process finished. ---")

if __name__ == "__main__":
    main()
