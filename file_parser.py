import re
import os
import requests
from dotenv import load_dotenv

# --- TMDb Setup ---
load_dotenv()
TMDB_API_KEY = os.getenv('TMDB_API_KEY')
TMDB_API_URL = "https://api.themoviedb.org/3"

if not TMDB_API_KEY:
    print("WARNING: TMDB_API_KEY environment variable not set. Parser will not be able to identify media type.")

def get_clean_search_query(filename):
    """Cleans the filename to produce the best possible search query for TMDB."""
    clean_name = os.path.splitext(filename)[0]
    clean_name = re.sub(r'\[.*?\]|\(.*?\)', '', clean_name)
    clean_name = re.sub(r'[._\s][sS]\d{1,2}[eE]\d{1,2}.*$', '', clean_name, flags=re.IGNORECASE)
    clean_name = re.sub(r'[._\s](19|20)\d{2}.*$', '', clean_name)
    tags = ['4K', '2160p', '1080p', '720p', '480p', 'HDTV', 'WEB-DL', 'WEBRip', 'BluRay', 'HDLight', 'MULTI', 'VOSTFR', 'TRUEFRENCH', 'FRENCH', 'VF']
    for tag in tags:
        clean_name = re.sub(r'[._\s]' + tag + r'[._\s]?', ' ', clean_name, flags=re.IGNORECASE)
    clean_name = re.sub(r'[._]', ' ', clean_name).strip()
    clean_name = re.sub(r'-\s*\w+$|', '', clean_name).strip()
    return clean_name

def parse_filename(filename):
    info = {
        'type': 'unknown',
        'title': filename,
        'season': None,
        'episode': None,
        'quality': None,
        'language': None,
        'year': None
    }

    search_query = get_clean_search_query(filename)
    tv_match = re.search(r'[._\s][sS](\d{1,2})[eE](\d{1,2})[._\s]', filename, re.IGNORECASE)

    if TMDB_API_KEY and search_query:
        try:
            endpoint = '/search/tv' if tv_match else '/search/movie'
            params = {'api_key': TMDB_API_KEY, 'query': search_query}
            response = requests.get(f"{TMDB_API_URL}{endpoint}", params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get('results'):
                top_result = data['results'][0]
                info['title'] = top_result.get('name' if tv_match else 'title')
                info['type'] = 'tv_show' if tv_match else 'movie'
                date_key = 'first_air_date' if tv_match else 'release_date'
                if top_result.get(date_key):
                    info['year'] = int(top_result[date_key].split('-')[0])

        except requests.exceptions.RequestException as e:
            print(f"ERROR: Could not query TMDb. Error: {e}")

    if tv_match:
        info['season'] = int(tv_match.group(1))
        info['episode'] = int(tv_match.group(2))

    quality_tags = ['4K', '2160p', '1080p', '720p', '480p', 'HDTV', 'WEB-DL', 'WEBRip', 'BluRay', 'HDLight']
    for tag in quality_tags:
        if tag.lower() in filename.lower():
            info['quality'] = tag
            break

    language_tags = ['MULTI', 'VOSTFR', 'TRUEFRENCH', 'FRENCH', 'VF']
    for tag in language_tags:
        if tag.lower() in filename.lower():
            info['language'] = tag
            break

    return info
