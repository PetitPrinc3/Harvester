# This script requires 'requests', 'beautifulsoup4', and 'thefuzz'.
# Please install them using: pip install requests beautifulsoup4 python-Levenshtein

import requests
import urllib.parse
import re
import json
import logging
from bs4 import BeautifulSoup
from thefuzz import fuzz

log = logging.getLogger(__name__)

# --- Scoring Constants ---
MAX_TITLE_SCORE = 100
MAX_LANG_SCORE = 25
MAX_MOVIE_QUALITY_SCORE = 4
MAX_SHOW_QUALITY_SCORE = 5
MAX_COMPLETENESS_SCORE = 30

MAX_MOVIE_SCORE = MAX_TITLE_SCORE + MAX_LANG_SCORE + MAX_MOVIE_QUALITY_SCORE
MAX_SHOW_RELEASE_SCORE = MAX_TITLE_SCORE + MAX_LANG_SCORE + MAX_SHOW_QUALITY_SCORE

class ZTParser:
    """A parser for Zone-Telechargement to find and select media."""

    def __init__(self, base_url):
        if not base_url.startswith('http'):
            raise ValueError("Base URL must start with http or https")
        self.base_url = base_url

    def _parse_results_from_page(self, soup):
        page_results = []
        for cover in soup.find_all('div', class_='cover_global'):
            title_anchor = cover.find('div', class_='cover_infos_title').find('a')
            if not title_anchor or not title_anchor.has_attr('href'):
                continue
            result_title = title_anchor.get_text(strip=True)
            relative_url = title_anchor['href']
            result_url = urllib.parse.urljoin(self.base_url, relative_url)
            quality, language = "N/A", "N/A"
            detail_span = cover.find('span', class_='detail_release')
            if detail_span:
                b_tags = detail_span.find_all('b')
                if len(b_tags) == 2:
                    quality = b_tags[0].get_text(strip=True)
                    language = b_tags[1].get_text(strip=True).strip('()')
                elif len(b_tags) == 1:
                    combined_text = b_tags[0].get_text(strip=True).strip('()')
                    quality = combined_text
                    language = combined_text
            page_results.append({
                "title": result_title, "url": result_url,
                "quality": quality, "language": language
            })
        return page_results

    def search(self, title, media_type):
        base_search_url = f"{self.base_url}/?p={media_type}&search={urllib.parse.quote_plus(title)}"
        all_results = []
        log.info(f"Querying page 1: {base_search_url}")
        try:
            response = requests.get(base_search_url, timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            log.error(f"An error occurred while fetching the first page: {e}")
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        all_results.extend(self._parse_results_from_page(soup))

        last_page = 1
        navigation = soup.find('div', class_='navigation')
        if navigation:
            for link in navigation.find_all('a'):
                if link.has_attr('href') and 'page=' in link['href']:
                    try:
                        page_num = int(link['href'].split('page=')[-1])
                        if page_num > last_page:
                            last_page = page_num
                    except (ValueError, IndexError):
                        continue
        
        if last_page > 1:
            log.info(f"Found {last_page} pages of results. Scraping remaining pages...")
            for page_num in range(2, last_page + 1):
                page_url = f"{base_search_url}&page={page_num}"
                log.info(f"Querying page {page_num}...")
                try:
                    response = requests.get(page_url, timeout=10)
                    response.raise_for_status()
                    soup = BeautifulSoup(response.text, 'html.parser')
                    all_results.extend(self._parse_results_from_page(soup))
                except requests.exceptions.RequestException as e:
                    log.warning(f"Could not fetch page {page_num}. Skipping. Error: {e}")
                    continue
        return all_results

    def verify_1fichier_link(self, page_url):
        try:
            response = requests.get(page_url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            provider_tag = soup.find('b', string=lambda t: t and '1fichier' in t.lower())
            if not provider_tag:
                return None
            link_tag = provider_tag.find_next_sibling('b').find('a')
            if link_tag and link_tag.has_attr('href'):
                return urllib.parse.urljoin(self.base_url, link_tag['href'])
            return None
        except requests.exceptions.RequestException as e:
            log.warning(f"Could not verify page {page_url}: {e}")
            return None

    def get_show_episode_links(self, page_url):
        try:
            response = requests.get(page_url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            provider_tag = soup.find('b', string=lambda t: t and '1fichier' in t.lower())
            if not provider_tag:
                return None

            episode_links = {}
            is_final = False
            for tag in provider_tag.find_next_siblings('b'):
                if tag.find('div'):
                    break
                link = tag.find('a')
                if link and link.has_attr('href'):
                    link_text = link.get_text(strip=True)
                    match = re.search(r'Episode (\d+)', link_text, re.IGNORECASE)
                    if match:
                        episode_number = int(match.group(1))
                        episode_links[episode_number] = urllib.parse.urljoin(self.base_url, link['href'])
                        if 'final' in link_text.lower():
                            is_final = True
            return {"links": episode_links, "is_final": is_final}
        except requests.exceptions.RequestException as e:
            log.warning(f"Could not verify page {page_url}: {e}")
            return None

def select_best_movie(parser, results, requested_title):
    log.info(f"--- Selecting best movie for '{requested_title}' ---")
    if not results:
        return None

    quality_preferences = ['hdlight 1080p', '4k light', 'hdlight', 'hd']
    SIMILARITY_THRESHOLD = 75

    scored_results = []
    for r in results:
        title_score = fuzz.token_set_ratio(requested_title, r['title'])
        if title_score < SIMILARITY_THRESHOLD:
            continue
        
        lang_lower = r['language'].lower()
        if 'multi' in lang_lower and 'truefrench' in lang_lower:
            lang_score = 25
        elif 'multi' in lang_lower:
            lang_score = 20
        elif 'truefrench' in lang_lower:
            lang_score = 15
        elif 'french' in lang_lower:
            lang_score = 10
        else:
            lang_score = 0

        quality_score = 0
        result_quality_lower = r['quality'].lower()
        for i, pref in enumerate(quality_preferences):
            if pref.endswith('*'):
                if result_quality_lower.startswith(pref[:-1]):
                    quality_score = len(quality_preferences) - i
                    break
            elif result_quality_lower == pref:
                quality_score = len(quality_preferences) - i
                break
        
        total_score = title_score + lang_score + quality_score
        scored_results.append({'result': r, 'score': total_score})

    if not scored_results:
        return None

    scored_results.sort(key=lambda x: x['score'], reverse=True)

    log.info(f"Found {len(scored_results)} potential candidates. Verifying for 1fichier link...")
    for candidate in scored_results:
        result_data = candidate['result']
        log.info(f"  Checking candidate: {result_data['title']} | Score: {candidate['score']}")
        dl_protect_link = parser.verify_1fichier_link(result_data['url'])
        if dl_protect_link:
            log.info(f"    -> SUCCESS: Found 1fichier link.")
            percentage_score = round((candidate['score'] / MAX_MOVIE_SCORE) * 100, 0)
            return {
                "title": result_data['title'],
                "url": result_data['url'],
                "quality": result_data['quality'],
                "language": result_data['language'],
                "dl_protect_link": dl_protect_link,
                "rating_score": f"{percentage_score}%"
            }
        else:
            log.warning("    -> FAILED: No 1fichier link found.")
    return None

def select_best_show(parser, results, requested_title, requested_season):
    log.info(f"--- Selecting best show for '{requested_title}' S{requested_season} ---")
    if not results:
        return None

    SIMILARITY_THRESHOLD = 85
    quality_preferences = ['VOSTFR HD', 'VF HD', 'VOSTFR', 'VF', 'VO']

    initial_candidates = []
    for r in results:
        title_similarity = fuzz.partial_ratio(requested_title.lower(), r['title'].lower())
        if title_similarity < SIMILARITY_THRESHOLD:
            continue
        season_match = re.search(r'saison\s*(\d+)', r['title'], re.IGNORECASE)
        if season_match and int(season_match.group(1)) == requested_season:
            r['found_season'] = int(season_match.group(1))
            initial_candidates.append(r)

    if not initial_candidates:
        return None

    top_candidates = initial_candidates[:4]
    log.info(f"Found {len(top_candidates)} potential candidates. Analyzing...")

    scored_candidates = []
    for candidate in top_candidates:
        log.info(f"  Checking candidate: {candidate['title']} ({candidate['quality']})")
        title_score = fuzz.partial_ratio(requested_title.lower(), candidate['title'].lower())
        
        lang_lower = candidate['language'].lower()
        if 'vostfr' in lang_lower:
            lang_score = 25
        elif 'vo' in lang_lower:
            lang_score = 20
        elif 'vf' in lang_lower:
            lang_score = 10
        else:
            lang_score = 0

        try:
            quality_score = len(quality_preferences) - quality_preferences.index(candidate['quality'])
        except ValueError:
            quality_score = 0

        episode_data = parser.get_show_episode_links(candidate['url'])
        completeness_score = 0
        if episode_data and episode_data['links']:
            completeness_score = 10
            episode_numbers = sorted(episode_data['links'].keys())
            is_consecutive = (episode_numbers == list(range(1, len(episode_numbers) + 1)))
            if is_consecutive:
                completeness_score = 20
            if is_consecutive and episode_data['is_final']:
                completeness_score = 30
        
        if completeness_score == 0:
            log.warning("    -> FAILED: No 1fichier links found.")
            continue

        release_score = title_score + lang_score + quality_score
        total_score = release_score + completeness_score
        log.info(f"    -> Score: {total_score}")
        candidate['episode_data'] = episode_data
        scored_candidates.append({'result': candidate, 'score': total_score, 'release_score': release_score, 'completeness_score': completeness_score})

    if not scored_candidates:
        return None

    scored_candidates.sort(key=lambda x: x['score'], reverse=True)
    best_candidate = scored_candidates[0]
    
    episode_list = [
        {"episode_number": num, "dl_protect_link": link}
        for num, link in sorted(best_candidate['result']['episode_data']['links'].items())
    ]
    
    release_percentage = round((best_candidate['release_score'] / MAX_SHOW_RELEASE_SCORE) * 100, 0)

    return {
        "title": requested_title,
        "season": best_candidate['result']['found_season'],
        "url": best_candidate['result']['url'],
        "quality": best_candidate['result']['quality'],
        "language": best_candidate['result']['language'],
        "rating_score": f"{release_percentage}%",
        "episode_data": episode_list
    }

if __name__ == '__main__':
    import logger_setup
    logger_setup.setup_logging()

    zt_base_url = "https://www.zone-telechargement.diy"
    parser = ZTParser(base_url=zt_base_url)

    # --- Movie Example ---
    movie_request_title = "Matrix Reloaded"
    movie_results = parser.search(movie_request_title, 'films')
    best_movie = select_best_movie(parser, movie_results, movie_request_title)
    if best_movie:
        log.info("--- Best Movie Result (JSON) ---")
        log.info(json.dumps(best_movie, indent=4))

    log.info("\n" + "="*80 + "\n")

    # --- TV Show Example ---
    show_request = {"title": "Big Bang", "season": 4}
    show_results = parser.search(show_request['title'], 'series')
    best_show = select_best_show(parser, show_results, show_request['title'], show_request['season'])
    if best_show:
        log.info("--- Best Show Result (JSON) ---")
        log.info(json.dumps(best_show, indent=4))
