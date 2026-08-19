import re
import aiohttp
import asyncio
import warnings
import logging
from io import BytesIO
from PIL import Image
from datetime import datetime
from difflib import SequenceMatcher
from info import IMAGE_FETCH, TMDB_API_KEY, MAX_LIST_ELM

logger = logging.getLogger(__name__)
LONG_IMDB_DESCRIPTION = False

Image.MAX_IMAGE_PIXELS = None
warnings.simplefilter("ignore", Image.DecompressionBombWarning)

# --- TMDB Configuration ---
TMDB_BEARER_TOKEN = 'eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiI2ZGU3YTIyZGU1YjE5YTFjNmUyZGU5ZWEyMzE2ZmQxMCIsIm5iZiI6MTc0NTMyMjQ2Mi41MzMsInN1YiI6IjY4MDc4MWRlYzVjODAzNWZiMDhhNjExNCIsInNjb3BlcyI6WyJhcGlfcmVhZCJdLCJ2ZXJzaW9uIjoxfQ.rMMJ2-PBIv8Y7ybxPIEpIlzTEXzuwrm9ruKxAUCAsbw'
TMDB_BASE_URL = 'https://api.themoviedb.org/3'
TMDB_IMAGE_BASE_URL = 'https://image.tmdb.org/t/p/original'
MIN_RUNTIME = 40

_session: aiohttp.ClientSession | None = None

async def get_session():
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15)
        )
    return _session

async def fetch_image(url, size=(860, 1200)):
    if not IMAGE_FETCH:
        logger.info("Image fetching is disabled.")
        return url
    try:
        session = await get_session()
        async with session.get(url, ssl=False) as response:
            if response.status != 200:
                logger.error(f"Failed to fetch image: {response.status} for {url}")
                return None
            data = await response.read()
            img = Image.open(BytesIO(data))
            img = img.resize(size, Image.LANCZOS)
            out = BytesIO()
            img.save(out, format="JPEG")
            out.seek(0)
            return out
    except aiohttp.ClientError as e:
        logger.error(f"HTTP request error in fetch_image: {e}")
    except IOError as e:
        logger.error(f"I/O error in fetch_image: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in fetch_image: {e}")
    return None

async def close_session():
    global _session
    if _session and not _session.closed:
        await _session.close()

def list_to_str(lst):
    if lst:
        return ", ".join(map(str, lst))
    return ""

def _list_to_str_tmdb(data_list, limit=10, key=None):
    """Helper for formatting TMDB response lists to comma-separated strings."""
    if not data_list or not isinstance(data_list, list):
        return None
    items = data_list[:limit]
    if key:
        return ", ".join(str(item.get(key, '')) for item in items if item)
    return ", ".join(str(item) for item in items if item)


def _extract_title_and_year(query: str):
    """Extract title and optional year from a search query string."""
    match = re.search(r'^(.*?)(?:\s+(\d{4}))?$', query.strip())
    if match:
        title, year_str = match.groups()
        year = int(year_str) if year_str and year_str.isdigit() else None
        return title.strip(), year
    return query.strip(), None


async def _tmdb_get(path, params=None, api_key=None):
    """Async GET request to TMDB API using aiohttp."""
    url = f"{TMDB_BASE_URL}/{path.lstrip('/')}"
    _params = params.copy() if params else {}
    _headers = {}

    if api_key:
        _params['api_key'] = api_key
    elif TMDB_BEARER_TOKEN:
        _headers = {
            'Authorization': f'Bearer {TMDB_BEARER_TOKEN}',
            'Content-Type': 'application/json;charset=utf-8'
        }

    session = await get_session()
    async with session.get(url, params=_params, headers=_headers, ssl=False) as resp:
        resp.raise_for_status()
        return await resp.json()


async def _fetch_media_details(media_type: str, media_id: int, api_key=None):
    """Fetch full details for a movie or TV show from TMDB."""
    params = {'append_to_response': 'credits,external_ids,alternative_titles,release_dates,images'}
    return await _tmdb_get(f"{media_type}/{media_id}", params=params, api_key=api_key)

async def _search_media_id(query: str, api_key=None):
    """Search TMDB for the best matching movie/TV show and return (media_type, media_id)."""
    title, year = _extract_title_and_year(query)
    multi_results = []
    words = title.split()
    
    # Generate up to 3 fallback queries to minimize API rate limit usage
    queries_to_try = [title]
    if len(words) > 2:
        queries_to_try.append(" ".join(words[:-1]))  # Drop the last word
        queries_to_try.append(words[0])              # Keep just the first word
    elif len(words) == 2:
        queries_to_try.append(words[0])
        
    # Remove any duplicates but preserve order, capping at 3 attempts
    queries_to_try = list(dict.fromkeys(queries_to_try))[:3]
    
    for target_query in queries_to_try:
        if not target_query:
            continue
        params = {'query': target_query, 'language': 'en-US', 'page': 1, 'include_adult': 'false'}
        try:
            result = await _tmdb_get('search/multi', params=params, api_key=api_key)
            multi_results = result.get('results', [])
            if multi_results:
                break
        except Exception as e:
            logger.error(f"Error searching multi in TMDB: {e}")
            continue

    def get_ratio(s1, s2):
        if not s1 or not s2:
            return 0
        return SequenceMatcher(None, s1.lower(), s2.lower()).ratio()

    # Pre-filter and score candidates without fetching details yet.
    # We will score them based on: ratio, whether year matches, and popularity.
    scored_results = []
    for r in multi_results:
        mtype = r.get('media_type')
        if mtype not in ['movie', 'tv']:
            continue

        r_title = r.get('title') or r.get('name')
        ratio = get_ratio(r_title, title)
        if ratio < 0.5:
            continue

        rd_str = r.get('release_date') or r.get('first_air_date')
        if not rd_str:
            continue
        try:
            rd_date = datetime.strptime(rd_str, '%Y-%m-%d').date()
        except ValueError:
            continue

        if year:
            if abs(rd_date.year - year) > 1:
                continue

        scored_results.append((r, ratio, rd_date))

    # If no results match with ratio >= 0.5, fall back to top 10 results from search
    if not scored_results:
        for r in multi_results[:10]:
            mtype = r.get('media_type')
            if mtype not in ['movie', 'tv']:
                continue

            r_title = r.get('title') or r.get('name')
            ratio = get_ratio(r_title, title)

            rd_str = r.get('release_date') or r.get('first_air_date')
            if not rd_str:
                continue
            try:
                rd_date = datetime.strptime(rd_str, '%Y-%m-%d').date()
            except ValueError:
                continue

            if year:
                if abs(rd_date.year - year) > 1:
                    continue
            scored_results.append((r, ratio, rd_date))

    if not scored_results:
        return None, None

    today = datetime.utcnow().date()
    candidates_past = []
    candidates_upcoming = []

    for r, ratio, rd_date in scored_results:
        candidate = {
            'type': r.get('media_type'),
            'id': r['id'],
            'date': rd_date,
            'score': r.get('popularity', 0),
            'ratio': ratio
        }
        if rd_date > today:
            candidates_upcoming.append(candidate)
        else:
            candidates_past.append(candidate)

    # Sort past candidates by: ratio (desc), date (desc), score (desc)
    candidates_past.sort(key=lambda x: (x['ratio'], x['date'], x['score']), reverse=True)
    # Sort upcoming candidates by: ratio (desc), date (desc), score (desc)
    candidates_upcoming.sort(key=lambda x: (x['ratio'], x['date'], x['score']), reverse=True)

    sorted_candidates = candidates_past + candidates_upcoming

    # Now, fetch details and check runtime/video status ONLY for the candidates we are considering,
    # sequentially in sorted order, until we find one that passes.
    for candidate in sorted_candidates:
        mtype = candidate['type']
        cid = candidate['id']

        if mtype == 'movie':
            try:
                details = await _fetch_media_details(mtype, cid, api_key=api_key)
                runtime = details.get('runtime')
                is_video = details.get('video', False)

                if is_video or (runtime and runtime < MIN_RUNTIME):
                    continue
            except Exception as e:
                logger.error(f"Error fetching movie details for validation: {e}")
                continue

        # If we got here, it's either a TV show or a movie that passed the validation.
        # This is our best candidate! We return it immediately.
        return mtype, cid

    return None, None

def _process_images(images_data):
    """Organize poster, backdrop and logo images by language."""
    posters_by_lang, backdrops_by_lang, logos_by_lang = {}, {}, {}
    for img in images_data.get('posters', []):
        lang = img.get('iso_639_1') or 'no_lang'
        posters_by_lang.setdefault(lang, []).append(f"{TMDB_IMAGE_BASE_URL}{img['file_path']}")
    for img in images_data.get('backdrops', []):
        lang = img.get('iso_639_1') or 'no_lang'
        backdrops_by_lang.setdefault(lang, []).append(f"{TMDB_IMAGE_BASE_URL}{img['file_path']}")
    for img in images_data.get('logos', []):
        lang = img.get('iso_639_1') or 'no_lang'
        logos_by_lang.setdefault(lang, []).append(f"{TMDB_IMAGE_BASE_URL}{img['file_path']}")
    posters_by_lang['all'] = [f"{TMDB_IMAGE_BASE_URL}{i['file_path']}" for i in images_data.get('posters', [])]
    backdrops_by_lang['all'] = [f"{TMDB_IMAGE_BASE_URL}{i['file_path']}" for i in images_data.get('backdrops', [])]
    logos_by_lang['all'] = [f"{TMDB_IMAGE_BASE_URL}{i['file_path']}" for i in images_data.get('logos', [])]
    languages = sorted(set(posters_by_lang) | set(backdrops_by_lang) | set(logos_by_lang))
    return {
        'posters': posters_by_lang,
        'backdrops': backdrops_by_lang,
        'logos': logos_by_lang,
        'available_languages': languages
    }


async def _fetch_tmdb_data(query: str, api_key=None):
    """
    Core TMDB lookup: search → fetch details → build response dict.
    This replaces the external tmdb.blazeposters.workers.dev API call.
    """
    media_type, media_id = await _search_media_id(query, api_key=api_key)
    if not media_id:
        return None

    details = await _fetch_media_details(media_type, media_id, api_key=api_key)
    crew = details.get('credits', {}).get('crew', [])

    certificates = None
    if media_type == 'movie' and 'release_dates' in details:
        us = [r for r in details['release_dates']['results'] if r['iso_3166_1'] == 'US']
        if us and us[0]['release_dates']:
            certificates = us[0]['release_dates'][0].get('certification')

    runtime_display = None
    if media_type == 'movie':
        runtime = details.get('runtime')
        runtime_display = f"{runtime} min" if runtime else None
    else:
        er = _list_to_str_tmdb(details.get('episode_run_time', []))
        runtime_display = f"{er} min" if er else None

    images_structured = _process_images(details.get('images', {}))
    images_structured['original_language'] = details.get('original_language')

    output_data = {
        'query': query, 'media_type': media_type, 'media_id': media_id,
        'title': details.get('title') or details.get('name'),
        'localized_title': details.get('original_title') or details.get('original_name'),
        'aka': _list_to_str_tmdb(details.get('alternative_titles', {}).get('titles', []), key='title'),
        'kind': media_type,
        'year': (details.get('release_date') or details.get('first_air_date', ''))[:4],
        'release_date': details.get('release_date') or details.get('first_air_date'),
        'imdb_id': details.get('external_ids', {}).get('imdb_id'),
        'tmdb_id': details.get('id'),
        'rating': details.get('vote_average'),
        'votes': details.get('vote_count'),
        'runtime': runtime_display,
        'certificates': certificates,
        'genres': _list_to_str_tmdb(details.get('genres', []), key='name'),
        'languages': _list_to_str_tmdb(details.get('spoken_languages', []), key='english_name'),
        'countries': _list_to_str_tmdb(details.get('production_countries', []), key='name'),
        'director': _list_to_str_tmdb([p for p in crew if p.get('job') == 'Director'], key='name'),
        'writer': _list_to_str_tmdb([p for p in crew if p.get('job') in ['Screenplay', 'Writer', 'Story']], key='name'),
        'producer': _list_to_str_tmdb([p for p in crew if p.get('job') == 'Producer'], key='name'),
        'composer': _list_to_str_tmdb([p for p in crew if p.get('job') == 'Original Music Composer'], key='name'),
        'cinematographer': _list_to_str_tmdb([p for p in crew if p.get('job') == 'Director of Photography'], key='name'),
        'cast': _list_to_str_tmdb(details.get('credits', {}).get('cast', []), key='name', limit=15),
        'plot': details.get('overview'),
        'tagline': details.get('tagline'),
        'box_office': details.get('revenue') if details.get('revenue', 0) > 0 else "N/A",
        'distributors': _list_to_str_tmdb(details.get('production_companies', []), key='name'),
        'poster_url': f"{TMDB_IMAGE_BASE_URL}{details.get('poster_path')}" if details.get('poster_path') else None,
        'url': f"https://www.themoviedb.org/{media_type}/{details.get('id')}",
        'images': images_structured,
    }

    if media_type == 'tv':
        output_data.update({
            'seasons': details.get('number_of_seasons'),
            'episodes': details.get('number_of_episodes'),
        })

    return output_data

async def get_movie_details(query, bulk=False, id=False, file=None):
    if not id:
        from utils import listx_to_str, imdb
        query = (query.strip()).lower()
        title = query
        year_val = None
        
        year_list = re.findall(r'[1-2]\d{3}$', query, re.IGNORECASE)
        if year_list:
            year_val = year_list[0]
            title = (query.replace(year_val, "")).strip()
        elif file is not None:
            year_list = re.findall(r'[1-2]\d{3}', file, re.IGNORECASE)
            if year_list:
                year_val = year_list[0]
        
        search_result = await asyncio.to_thread(imdb.search_movie, title.lower())
        if not search_result or not search_result.titles:
            return None
        
        movie_list = search_result.titles[:MAX_LIST_ELM]
        
        if year_val:
            filtered = [m for m in movie_list if m.year and str(m.year) == str(year_val)]
            if not filtered:
                filtered = movie_list
        else:
            filtered = movie_list
            
        kind_filter = ['movie', 'tv series', 'tvSeries', 'tvMiniSeries', 'tvMovie']
        filtered_kind = [m for m in filtered if m.kind and m.kind in kind_filter]
        
        if not filtered_kind:
            filtered_kind = filtered
        
        if bulk:
            return filtered_kind[:MAX_LIST_ELM]
        if not filtered_kind:
            return None   
        movie_brief = filtered_kind[0]
        movieid_str = movie_brief.imdb_id 
    else:
        movieid_str = query

    movie = await asyncio.to_thread(imdb.get_movie, movieid_str)
    if not movie:
        return None

    if movie.release_date:
        date = movie.release_date
    elif movie.year:
        date = str(movie.year)
    else:
        date = "N/A"
        
    plot = movie.plot[0] if isinstance(movie.plot, list) else movie.plot or ""
    if len(plot) > 800:
        plot = plot[:800] + "..."
    imdb_id = movie.imdb_id
    if not imdb_id.startswith("tt"):
        imdb_id = f"tt{imdb_id}"
    return {
        'title': movie.title,
        'votes': movie.votes,
        "aka": listx_to_str(movie.title_akas),
        "seasons": (
            len(movie.info_series.display_seasons)
            if getattr(movie, "info_series", None)
            and getattr(movie.info_series, "display_seasons", None)
            else "N/A"
        ),
        "box_office": movie.worldwide_gross,
        'localized_title': movie.title_localized,
        'kind': movie.kind,
        "imdb_id": imdb_id,
        "cast": listx_to_str(movie.stars),
        "runtime": listx_to_str(movie.duration),
        "countries": listx_to_str(movie.countries),
        "certificates": listx_to_str(movie.certificates),
        "languages": listx_to_str(movie.languages),
        "director": listx_to_str(movie.directors),
        "writer": listx_to_str([p.name for p in movie.writers]),
        "producer": listx_to_str([p.name for p in movie.producers]),
        "composer": listx_to_str([p.name for p in movie.composers]),
        "cinematographer": listx_to_str([p.name for p in movie.cinematographers]),
        "music_team": listx_to_str([p.name for p in movie.music_team]),
        "distributors": listx_to_str([c.name for c in movie.distributors]),        
        'release_date': date,
        'year': movie.year,
        'genres': listx_to_str(movie.genres),
        'poster': movie.cover_url,
        'poster_url': movie.cover_url.split("._V1_")[0] + "._V1_SX500.jpg" if movie.cover_url and "._V1_" in movie.cover_url else movie.cover_url,
        'plot': plot,
        'rating': str(movie.rating),
        "url": movie.url or f"https://www.imdb.com/title/{imdb_id}"
    }

r"""
async def old_get_movie_details(query, id=False, file=None):
    try:
        if not id:
            query = query.strip().lower()
            title = query
            year = re.findall(r'[1-2]\d{3}$', query, re.IGNORECASE)
            if year:
                year = list_to_str(year[:1])
                title = query.replace(year, "").strip()
            elif file is not None:
                year = re.findall(r'[1-2]\d{3}', file, re.IGNORECASE)
                if year:
                    year = list_to_str(year[:1])
            else:
                year = None
            movieid = ia.search_movie(title.lower(), results=10)
            if not movieid:
                return None
            if year:
                filtered = list(filter(lambda k: str(k.get('year')) == str(year), movieid))
                if not filtered:
                    filtered = movieid
            else:
                filtered = movieid
            filtered_kind = list(filter(lambda k: k.get('kind') in ['movie', 'tv series'], filtered))
            if not filtered_kind:
                logger.info("No matches found for kind 'movie' or 'tv series', falling back to filtered list.")
                movieid = filtered
            else:
                movieid = filtered_kind
            movieid = movieid[0].movieID
        else:
            movieid = query
        movie = ia.get_movie(movieid)
        ia.update(movie, info=['main', 'vote details'])
        if movie.get("original air date"):
            date = movie["original air date"]
        elif movie.get("year"):
            date = movie.get("year")
        else:
            date = "N/A"
        plot = movie.get('plot')
        if plot and len(plot) > 0:
            plot = plot[0]
        else:
            plot = movie.get('plot outline')
        if plot and len(plot) > 800:
            plot = plot[:800] + "..."
        poster_url = movie.get('full-size cover url')
        return {
            'title': movie.get('title'),
            'votes': movie.get('votes'),
            "aka": list_to_str(movie.get("akas")),
            "seasons": movie.get("number of seasons"),
            "box_office": movie.get('box office'),
            'localized_title': movie.get('localized title'),
            'kind': movie.get("kind"),
            "imdb_id": f"tt{movie.get('imdbID')}",
            "cast": list_to_str(movie.get("cast")),
            "runtime": list_to_str(movie.get("runtimes")),
            "countries": list_to_str(movie.get("countries")),
            "certificates": list_to_str(movie.get("certificates")),
            "languages": list_to_str(movie.get("languages")),
            "director": list_to_str(movie.get("director")),
            "writer": list_to_str(movie.get("writer")),
            "producer": list_to_str(movie.get("producer")),
            "composer": list_to_str(movie.get("composer")),
            "cinematographer": list_to_str(movie.get("cinematographer")),
            "music_team": list_to_str(movie.get("music department")),
            "distributors": list_to_str(movie.get("distributors")),
            'release_date': date,
            'year': movie.get('year'),
            'genres': list_to_str(movie.get("genres")),
            'poster_url': poster_url + "._V1_SX1440.jpg" if poster_url.endswith("@.jpg") else poster_url,
            'plot': plot,
            'rating': str(movie.get("rating", "N/A")),
            'url': f'https://www.imdb.com/title/tt{movieid}'
        }
    except Exception as e:
        logger.exception(f"An error occurred in get_movie_details: {e}")
        return None
"""

async def get_movie_detailsx(query, id=False, file=None):
    q = str(query).strip()
    try:
        data = await _fetch_tmdb_data(q, api_key=TMDB_API_KEY or None)
        if not data:
            logger.warning(f"TMDB returned no results for '{q}' → switching to IMDb fallback")
            return await get_movie_details(q)
    except Exception as e:
        logger.error(f"TMDB direct call failed → fallback IMDb: {e}")
        return await get_movie_details(q)

    details = {}
    details['title'] = data.get('title') or data.get('localized_title')
    details['year'] = (data.get('year', 0)) if data.get('year') else None
    details['release_date'] = data.get('release_date')
    details['rating'] = round(float(data.get('rating', 0)), 1) if data.get('rating') is not None else None
    details['votes'] = int(data.get('votes', 0))
    details['runtime'] = data.get('runtime')
    details['certificates'] = data.get('certificates')
    details['tmdb_url'] = data.get('url')
    for key in ('genres', 'languages', 'countries'):
        raw = data.get(key)
        details[key] = [s.strip() for s in raw.split(',')] if raw else []
    for role in ('director', 'writer', 'producer', 'composer', 'cinematographer', 'cast'):
        raw = data.get(role)
        details[role] = [s.strip() for s in raw.split(',')] if raw else []
    details['plot'] = data.get('plot')
    details['tagline'] = data.get('tagline')
    details['box_office'] = (data.get('box_office', 0)) if data.get('box_office') else None
    raw_dist = data.get('distributors')
    details['distributors'] = [d.strip() for d in raw_dist.split(',')] if raw_dist else []
    details['imdb_id'] = data.get('imdb_id')
    details['tmdb_id'] = data.get('tmdb_id')
    posters = data.get('images', {}).get('posters', {})
    original_language = data.get('images', {}).get('original_language')
    poster_url = data.get('poster_url')
    if not poster_url:
        for key in ('en', original_language, 'xx'):
            if key and posters.get(key):
                poster_url = posters[key][0]
                break
    details['poster_url'] = poster_url.replace("/original/", "/w500/") if poster_url else None

    logos = data.get('images', {}).get('logos', {})
    original_language = data.get('images', {}).get('original_language')
    logo_url = None
    for key in ('en', original_language, 'xx', 'no_lang'):
        if key and logos.get(key):
            logo_url = logos[key][0]
            break
    if not logo_url and logos.get('all'):
        logo_url = logos['all'][0]
    details['logo_url'] = logo_url.replace("/original/", "/w500/") if logo_url else None

    backdrops = data.get('images', {}).get('backdrops', {})
    backdrop_url = None
    for key in ('en', original_language, 'xx', 'no_lang'):
        if key and backdrops.get(key):
            backdrop_url = backdrops[key][0]
            break
    details['backdrop_url'] = backdrop_url.replace("/original/", "/w780/") if backdrop_url else None
    return details


async def fetch_image_bytes(url):
    try:
        session = await get_session()
        async with session.get(url, ssl=False) as response:
            if response.status != 200:
                logger.error(f"Failed to fetch image: {response.status} for {url}")
                return None
            return await response.read()
    except Exception as e:
        logger.error(f"Error fetching image bytes: {e}")
        return None


def draw_telegram_logo(draw, cx, cy, r):
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill='#33A5E4')
    scale = r / 10.0
    p1 = [
        (cx + 6.5 * scale, cy - 6 * scale),
        (cx - 6.5 * scale, cy - 0.5 * scale),
        (cx - 0.5 * scale, cy + 1.5 * scale),
    ]
    p2 = [
        (cx + 6.5 * scale, cy - 6 * scale),
        (cx - 0.5 * scale, cy + 1.5 * scale),
        (cx + 1.5 * scale, cy + 2.5 * scale),
    ]
    p3 = [
        (cx - 0.5 * scale, cy + 1.5 * scale),
        (cx - 1.5 * scale, cy + 5.5 * scale),
        (cx + 1.5 * scale, cy + 2.5 * scale),
    ]
    draw.polygon(p1, fill='white')
    draw.polygon(p2, fill='#E5E5E5')
    draw.polygon(p3, fill='#B5B5B5')


def _draw_landscape_poster_sync(backdrop_bytes, poster_bytes, logo_bytes, title, description, genres, year, season_info, rating="N/A", runtime=None):
    import os
    import math
    from PIL import ImageDraw, ImageFont, ImageFilter, ImageOps, ImageChops
    from io import BytesIO
    import re

    canvas_w, canvas_h = 1280, 720

    # Create dark slate background
    bg_img = Image.new('RGB', (canvas_w, canvas_h), color='#0d0e11')

    if backdrop_bytes:
        try:
            bd_img = Image.open(BytesIO(backdrop_bytes))
            bd_img = ImageOps.fit(bd_img, (canvas_w, canvas_h), centering=(0.5, 0.5))
            bg_img.paste(bd_img, (0, 0))
        except Exception as e:
            logger.error(f"Failed to open backdrop: {e}")

    # Smooth horizontal and vertical dark gradient overlay for text legibility
    alpha_h_bytes = bytes(int(max(0, (1.0 - (x / 750.0)) * 220)) for x in range(canvas_w))
    alpha_v_bytes = bytes(min(255, max(0, int(((y - 150) / 500.0) * 200))) for y in range(canvas_h))
    alpha_h_img = Image.frombytes('L', (canvas_w, 1), alpha_h_bytes).resize((canvas_w, canvas_h), Image.Resampling.NEAREST)
    alpha_v_img = Image.frombytes('L', (1, canvas_h), alpha_v_bytes).resize((canvas_w, canvas_h), Image.Resampling.NEAREST)
    alpha_img = ImageChops.lighter(alpha_h_img, alpha_v_img)

    black_img = Image.new('L', (canvas_w, canvas_h), 0)
    overlay = Image.merge('RGBA', (black_img, black_img, black_img, alpha_img))
    bg_img = Image.alpha_composite(bg_img.convert('RGBA'), overlay).convert('RGB')

    draw = ImageDraw.Draw(bg_img)

    font_path_bold = "fonts/LiberationSans-Bold.ttf"
    font_path_reg = "fonts/LiberationSans-Regular.ttf"

    if not os.path.exists(font_path_bold):
        font_path_bold = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
    if not os.path.exists(font_path_reg):
        font_path_reg = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"

    if not os.path.exists(font_path_bold):
        font_path_bold = None
    if not os.path.exists(font_path_reg):
        font_path_reg = None

    try:
        title_font = ImageFont.truetype(font_path_bold, 42) if font_path_bold else ImageFont.load_default()
        badge_font = ImageFont.truetype(font_path_bold, 15) if font_path_bold else ImageFont.load_default()
        plot_font = ImageFont.truetype(font_path_reg, 18) if font_path_reg else ImageFont.load_default()
        promo_head_font = ImageFont.truetype(font_path_bold, 13) if font_path_bold else ImageFont.load_default()
        promo_title_font = ImageFont.truetype(font_path_bold, 22) if font_path_bold else ImageFont.load_default()
        promo_sub_font = ImageFont.truetype(font_path_reg, 12) if font_path_reg else ImageFont.load_default()
        imdb_val_font = ImageFont.truetype(font_path_bold, 32) if font_path_bold else ImageFont.load_default()
        imdb_lbl_font = ImageFont.truetype(font_path_bold, 11) if font_path_bold else ImageFont.load_default()
        footer_font = ImageFont.truetype(font_path_bold, 15) if font_path_bold else ImageFont.load_default()
    except Exception as e:
        logger.error(f"Font load error: {e}")
        title_font = badge_font = plot_font = promo_head_font = promo_title_font = promo_sub_font = imdb_val_font = imdb_lbl_font = footer_font = ImageFont.load_default()

    # --- 1. Top Right IMDb Rating Box ---
    r_str = str(rating or "N/A").strip()
    try:
        r_num = float(r_str)
        rating_display = f"{r_num:.1f}"
    except (ValueError, TypeError):
        rating_display = "N/A" if r_str in ["N/A", "None", ""] else r_str

    imdb_box_x, imdb_box_y = 1040, 35
    imdb_box_w, imdb_box_h = 180, 115

    # Translucent card background with golden accent outline
    card_bg = Image.new('RGBA', (canvas_w, canvas_h), (0, 0, 0, 0))
    card_draw = ImageDraw.Draw(card_bg)
    card_draw.rounded_rectangle(
        [imdb_box_x, imdb_box_y, imdb_box_x + imdb_box_w, imdb_box_y + imdb_box_h],
        radius=14,
        fill=(18, 18, 20, 190),
        outline=(180, 140, 50, 220),
        width=1
    )
    bg_img = Image.alpha_composite(bg_img.convert('RGBA'), card_bg).convert('RGB')
    draw = ImageDraw.Draw(bg_img)

    # Draw Laurel Wreath around rating
    center_x = imdb_box_x + (imdb_box_w // 2)
    center_y = imdb_box_y + 36

    # Draw Left and Right Laurel Branches (gold arcs with leaves)
    gold_color = (235, 195, 45)
    for side in (-1, 1):
        for deg in range(-70, 70, 20):
            rad = math.radians(deg)
            lx = center_x + side * (38 + math.sin(rad) * 4)
            ly = center_y + math.sin(rad) * 22
            angle = rad * side
            # Draw leaf
            leaf_len = 8
            x2 = lx + side * math.cos(angle) * leaf_len
            y2 = ly + math.sin(angle) * leaf_len
            draw.line([(lx, ly), (x2, y2)], fill=gold_color, width=2)

    # Draw Rating Value
    r_bbox = draw.textbbox((0, 0), rating_display, font=imdb_val_font)
    r_w = r_bbox[2] - r_bbox[0]
    r_h = r_bbox[3] - r_bbox[1]
    draw.text((center_x - r_w // 2, center_y - r_h // 2 - r_bbox[1]), rating_display, fill='white', font=imdb_val_font)

    # IMDb Label
    lbl_text = "IMDb RATING"
    lbl_bbox = draw.textbbox((0, 0), lbl_text, font=imdb_lbl_font)
    lbl_w = lbl_bbox[2] - lbl_bbox[0]
    draw.text((center_x - lbl_w // 2, imdb_box_y + 68), lbl_text, fill=gold_color, font=imdb_lbl_font)

    # Star Rating Row (5 stars)
    star_y = imdb_box_y + 88
    total_stars_w = 5 * 14 + 4 * 4
    start_star_x = center_x - total_stars_w // 2

    # Calculate filled stars based on r_num out of 10 (scale to 5 stars)
    try:
        filled_stars = int(round(r_num / 2.0))
    except (ValueError, UnboundLocalError):
        filled_stars = 3

    for s_idx in range(5):
        sx = start_star_x + s_idx * 18 + 7
        sy = star_y + 7
        r_out, r_in = 6, 2.5
        points = []
        for idx in range(10):
            r = r_out if idx % 2 == 0 else r_in
            angle = idx * math.pi / 5 - math.pi / 2
            px = sx + r * math.cos(angle)
            py = sy + r * math.sin(angle)
            points.append((px, py))
        s_fill = gold_color if s_idx < filled_stars else (90, 90, 90)
        draw.polygon(points, fill=s_fill)

    # --- 2. Middle Left Title ---
    left_x = 60
    title_text = str(title or "").upper().strip()

    title_lines = []
    current_line = ""
    for word in title_text.split():
        test_line = f"{current_line} {word}".strip()
        bbox = draw.textbbox((0, 0), test_line, font=title_font)
        if bbox[2] - bbox[0] < 650:
            current_line = test_line
        else:
            if current_line:
                title_lines.append(current_line)
            current_line = word
    if current_line:
        title_lines.append(current_line)
    title_lines = title_lines[:2]

    title_start_y = 250
    curr_y = title_start_y
    for line in title_lines:
        draw.text((left_x, curr_y), line, fill='white', font=title_font)
        bbox = draw.textbbox((0, 0), line, font=title_font)
        curr_y += (bbox[3] - bbox[1]) + 8

    # Subtle colored underline under title
    underline_w = min(120, max(60, int((draw.textbbox((0, 0), title_lines[0], font=title_font)[2] - left_x) * 0.35))) if title_lines else 80
    draw.rectangle([left_x, curr_y + 2, left_x + underline_w, curr_y + 5], fill=(195, 160, 90))

    # --- 3. Pill Badges Row ---
    curr_y += 24

    def draw_badge(x, y, text):
        nonlocal bg_img, draw
        bbox = draw.textbbox((0, 0), text, font=badge_font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        pw = tw + 28
        ph = 32

        badge_layer = Image.new('RGBA', (canvas_w, canvas_h), (0, 0, 0, 0))
        bl_draw = ImageDraw.Draw(badge_layer)
        bl_draw.rounded_rectangle([x, y, x + pw, y + ph], radius=ph // 2, fill=(35, 35, 40, 200))
        bg_img = Image.alpha_composite(bg_img.convert('RGBA'), badge_layer).convert('RGB')
        draw = ImageDraw.Draw(bg_img)

        tx = x + 14
        ty = y + (ph - th) // 2 - bbox[1]
        draw.text((tx, ty), text, fill='white', font=badge_font)
        return pw

    # Badges list: Runtime, Genres, Year, Certificate/Type
    def format_runtime_str(runtime_val):
        if not runtime_val or runtime_val == "N/A":
            return None
        m = re.search(r'(\d+)', str(runtime_val))
        if m:
            minutes = int(m.group(1))
            h = minutes // 60
            mins = minutes % 60
            return f"{h}H {mins}M" if h > 0 else f"{mins}M"
        return str(runtime_val).upper()

    badges = []
    fmt_rt = format_runtime_str(runtime)
    if fmt_rt:
        badges.append(fmt_rt)

    # Add genres
    genres_list = []
    if isinstance(genres, list):
        genres_list = [g.strip().upper() for g in genres if g.strip()][:2]
    elif isinstance(genres, str) and genres:
        genres_list = [g.strip().upper() for g in genres.split(",") if g.strip() and g.strip().upper() != 'N/A'][:2]
    badges.extend(genres_list)

    if year and str(year).strip() != "N/A":
        badges.append(str(year).strip())

    type_badge = "SERIES" if season_info and "SEASON" in str(season_info).upper() else "PG-13"
    badges.append(type_badge)

    bx = left_x
    for b_text in badges:
        bw = draw_badge(bx, curr_y, b_text)
        bx += bw + 10

    # --- 4. Plot Description ---
    curr_y += 48
    desc_text = str(description or "").strip()

    if desc_text:
        words = desc_text.split()
        plot_lines = []
        c_line = ""
        for w in words:
            t_line = f"{c_line} {w}".strip()
            bbox = draw.textbbox((0, 0), t_line, font=plot_font)
            if bbox[2] - bbox[0] <= 580:
                c_line = t_line
            else:
                if c_line:
                    plot_lines.append(c_line)
                c_line = w
                if len(plot_lines) == 2:
                    plot_lines[-1] = plot_lines[-1].rstrip(".,!?;:") + "..."
                    break
        if c_line and len(plot_lines) < 2:
            plot_lines.append(c_line)

        for line in plot_lines:
            draw.text((left_x, curr_y), line, fill=(225, 225, 225), font=plot_font)
            bbox = draw.textbbox((0, 0), line, font=plot_font)
            curr_y += (bbox[3] - bbox[1]) + 6

    # --- 5. Telegram Promo Card (Bottom Left) ---
    promo_x, promo_y = left_x, 520
    promo_w, promo_h = 440, 92

    p_card = Image.new('RGBA', (canvas_w, canvas_h), (0, 0, 0, 0))
    p_draw = ImageDraw.Draw(p_card)
    p_draw.rounded_rectangle(
        [promo_x, promo_y, promo_x + promo_w, promo_y + promo_h],
        radius=14,
        fill=(24, 20, 18, 210),
        outline=(170, 125, 60, 220),
        width=1
    )
    bg_img = Image.alpha_composite(bg_img.convert('RGBA'), p_card).convert('RGB')
    draw = ImageDraw.Draw(bg_img)

    # Blue Telegram Icon inside card
    tg_icon_cx = promo_x + 36
    tg_icon_cy = promo_y + promo_h // 2
    draw_telegram_logo(draw, tg_icon_cx, tg_icon_cy, r=18)

    # Texts inside card
    tx_start = promo_x + 72
    draw.text((tx_start, promo_y + 14), "EXCLUSIVELY ON TELEGRAM", fill=(215, 175, 75), font=promo_head_font)
    draw.text((tx_start, promo_y + 32), "@cholochhitro", fill='white', font=promo_title_font)
    draw.text((tx_start, promo_y + 62), "Your Destination For Quality Movies", fill=(180, 180, 180), font=promo_sub_font)

    # --- 6. Bottom Footer Bar ---
    footer_line_y = 672
    draw.line([(0, footer_line_y), (canvas_w, footer_line_y)], fill=(120, 90, 45), width=1)

    # Centered "STAY CONNECTED [TG ICON] @cholochhitro"
    t1 = "STAY CONNECTED"
    t2 = "@cholochhitro"
    b1 = draw.textbbox((0, 0), t1, font=footer_font)
    b2 = draw.textbbox((0, 0), t2, font=footer_font)
    w1 = b1[2] - b1[0]
    w2 = b2[2] - b2[0]

    tg_r = 10
    gap = 12
    total_footer_w = w1 + gap + (2 * tg_r) + gap + w2
    footer_start_x = (canvas_w - total_footer_w) // 2
    footer_y = footer_line_y + 15

    draw.text((footer_start_x, footer_y), t1, fill='white', font=footer_font)

    icon_cx = footer_start_x + w1 + gap + tg_r
    icon_cy = footer_y + (b1[3] - b1[1]) // 2 + 1
    draw_telegram_logo(draw, icon_cx, icon_cy, r=tg_r)

    t2_x = icon_cx + tg_r + gap
    draw.text((t2_x, footer_y), t2, fill='white', font=footer_font)

    out = BytesIO()
    bg_img.save(out, format="JPEG", quality=85)
    out.seek(0)
    return out


async def generate_landscape_poster(title, description, genres, year, season_info, backdrop_url, poster_url, logo_url=None, rating="N/A", runtime=None):
    import asyncio

    tasks = []
    if backdrop_url:
        tasks.append(fetch_image_bytes(backdrop_url))
    else:
        tasks.append(asyncio.sleep(0, result=None))

    if poster_url:
        tasks.append(fetch_image_bytes(poster_url))
    else:
        tasks.append(asyncio.sleep(0, result=None))

    if logo_url:
        tasks.append(fetch_image_bytes(logo_url))
    else:
        tasks.append(asyncio.sleep(0, result=None))

    backdrop_bytes, poster_bytes, logo_bytes = await asyncio.gather(*tasks)

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        _draw_landscape_poster_sync,
        backdrop_bytes,
        poster_bytes,
        logo_bytes,
        title,
        description,
        genres,
        year,
        season_info,
        rating,
        runtime
    )
