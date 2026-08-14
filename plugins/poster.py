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
    from PIL import ImageDraw, ImageFont, ImageFilter, ImageOps
    from io import BytesIO
    import re

    canvas_w, canvas_h = 1280, 720

    # Create solid modern slate-black background
    bg_img = Image.new('RGB', (canvas_w, canvas_h), color='#111215')

    if backdrop_bytes:
        try:
            bd_img = Image.open(BytesIO(backdrop_bytes))
            bd_img = ImageOps.fit(bd_img, (canvas_w, canvas_h), centering=(0.5, 0.5))
            bg_img.paste(bd_img, (0, 0))
        except Exception as e:
            logger.error(f"Failed to open backdrop: {e}")

    # Create smooth horizontal and vertical dark gradient overlay for text readability
    # Fades to dark on the bottom and left
    overlay = Image.new('RGBA', (canvas_w, canvas_h), (0, 0, 0, 0))
    pixels = []
    for y in range(canvas_h):
        for x in range(canvas_w):
            # Horizontal gradient (fade out from left to right)
            if x < 800:
                alpha_h = int((1.0 - (x / 800.0)) * 210)
            else:
                alpha_h = 0

            # Vertical gradient (fade out from bottom to top)
            if y > 250:
                alpha_v = int(((y - 250) / 415.0) * 210)
            else:
                alpha_v = 0

            alpha = max(alpha_h, alpha_v)
            pixels.append((0, 0, 0, alpha))
    overlay.putdata(pixels)
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
        title_font = ImageFont.truetype(font_path_bold, 48) if font_path_bold else ImageFont.load_default()
        desc_font = ImageFont.truetype(font_path_reg, 19) if font_path_reg else ImageFont.load_default()
        badge_font = ImageFont.truetype(font_path_bold, 18) if font_path_bold else ImageFont.load_default()
        copyright_font = ImageFont.truetype(font_path_bold, 24) if font_path_bold else ImageFont.load_default()
    except Exception as e:
        logger.error(f"Font load error: {e}")
        title_font = desc_font = badge_font = copyright_font = ImageFont.load_default()

    # --- Draw Title (Logo or Normal Text) ---
    logo_drawn = False
    if logo_bytes:
        try:
            logo_img = Image.open(BytesIO(logo_bytes))
            if logo_img.mode != 'RGBA':
                logo_img = logo_img.convert('RGBA')
            lw, lh = logo_img.size
            aspect = lw / lh
            # Try matching max height first
            new_h = 120
            new_w = int(new_h * aspect)
            if new_w > 400:
                new_w = 400
                new_h = int(new_w / aspect)
            logo_resized = logo_img.resize((new_w, new_h), Image.Resampling.LANCZOS)

            temp_logo = Image.new('RGBA', (canvas_w, canvas_h), (0, 0, 0, 0))
            # Paste logo on left side, directly above badges (y_badges = 510, with margin bottom of logo is y=490)
            logo_x = 50
            logo_y = 490 - new_h
            temp_logo.paste(logo_resized, (logo_x, logo_y))
            bg_img = Image.alpha_composite(bg_img.convert('RGBA'), temp_logo).convert('RGB')
            draw = ImageDraw.Draw(bg_img)
            logo_drawn = True
        except Exception as e:
            logger.error(f"Failed to load/draw movie logo: {e}")

    if not logo_drawn:
        # Fall back to normal text title
        title_text = str(title).upper()
        # Wrap title
        title_lines = []
        current_line = ""
        for word in title_text.split():
            test_line = f"{current_line} {word}".strip()
            bbox = draw.textbbox((0, 0), test_line, font=title_font)
            line_w = bbox[2] - bbox[0]
            if line_w < 750:
                current_line = test_line
            else:
                if current_line:
                    title_lines.append(current_line)
                current_line = word
        if current_line:
            title_lines.append(current_line)

        title_lines = title_lines[:2] # Limit text title to 2 lines
        title_y = 490
        # Calculate total height to offset title_y
        total_title_h = 0
        line_heights = []
        for line in title_lines:
            bbox = draw.textbbox((0, 0), line, font=title_font)
            line_heights.append(bbox[3] - bbox[1])
            total_title_h += (bbox[3] - bbox[1]) + 10

        y_cursor = title_y - total_title_h
        for i, line in enumerate(title_lines):
            draw.text((50, y_cursor), line, fill='white', font=title_font)
            y_cursor += line_heights[i] + 10

    # --- Draw Badges (Pills) ---
    def draw_pill(draw, x, y, text, font, bg_color, text_color='white', border_color=None, border_width=2):
        has_star = text.startswith("★")
        display_text = text[1:].strip() if has_star else text

        bbox = draw.textbbox((0, 0), display_text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        bx_offset = bbox[1]

        star_w = 22 if has_star else 0
        pill_w = tw + 32 + star_w
        pill_h = 36

        if bg_color is None: # transparent/border-only badge
            draw.rounded_rectangle([x, y, x + pill_w, y + pill_h], radius=pill_h // 2, outline=border_color, width=border_width)
        else:
            draw.rounded_rectangle([x, y, x + pill_w, y + pill_h], radius=pill_h // 2, fill=bg_color)

        tx = x + 16
        if has_star:
            import math
            star_cx = x + 24
            star_cy = y + 18
            r_out = 9
            r_in = 4
            points = []
            for idx in range(10):
                r = r_out if idx % 2 == 0 else r_in
                angle = idx * math.pi / 5 - math.pi / 2
                sx = star_cx + r * math.cos(angle)
                sy = star_cy + r * math.sin(angle)
                points.append((sx, sy))
            draw.polygon(points, fill='#FFD700') # Gold star
            tx += star_w

        ty = y + (pill_h - th) // 2 - bx_offset
        draw.text((tx, ty), display_text, fill=text_color, font=font)
        return pill_w

    # Row 1 Badges (Rating, IMDb, Year) at y = 510
    badge_x = 50
    badge_y1 = 510

    # 1. Rating
    r_val = str(rating or "N/A").strip()
    if r_val and r_val != "N/A":
        badge_x += draw_pill(draw, badge_x, badge_y1, f"★ {r_val}", badge_font, bg_color='#E58E26') + 12

    # 2. IMDb
    badge_x += draw_pill(draw, badge_x, badge_y1, "IMDb", badge_font, bg_color='#F5C518', text_color='black') + 12

    # 3. Year
    year_str = str(year or "2024").strip()
    draw_pill(draw, badge_x, badge_y1, year_str, badge_font, bg_color=None, border_color='white', border_width=2)

    # Row 2 Badges (Type, Runtime, Genres) at y = 560
    badge_x = 50
    badge_y2 = 560

    # 1. Type
    type_str = "SERIES" if season_info and "SEASON" in str(season_info).upper() else "MOVIE"
    badge_x += draw_pill(draw, badge_x, badge_y2, type_str, badge_font, bg_color='#D63031') + 12

    # 2. Runtime
    def format_runtime(runtime_str):
        if not runtime_str or runtime_str == "N/A":
            return None
        match = re.search(r'(\d+)', str(runtime_str))
        if match:
            minutes = int(match.group(1))
            hours = minutes // 60
            mins = minutes % 60
            if hours > 0:
                return f"{hours}H {mins}M" if mins > 0 else f"{hours}H"
            return f"{mins}M"
        return None

    fmt_runtime = format_runtime(runtime)
    if fmt_runtime:
        badge_x += draw_pill(draw, badge_x, badge_y2, fmt_runtime, badge_font, bg_color='#8E44AD') + 12

    # 3. Genres
    genres_to_draw = []
    if isinstance(genres, list):
        genres_to_draw = [g.strip().upper() for g in genres if g.strip()][:2]
    elif isinstance(genres, str) and genres:
        genres_to_draw = [g.strip().upper() for g in genres.split(",") if g.strip() and g.strip().upper() != 'N/A'][:2]

    genre_colors = ['#2980B9', '#D35400']
    for idx, genre_text in enumerate(genres_to_draw):
        color = genre_colors[idx] if idx < len(genre_colors) else '#2980B9'
        badge_x += draw_pill(draw, badge_x, badge_y2, genre_text, badge_font, bg_color=color) + 12

    # --- Draw Plot (max 2 lines) at y = 612 ---
    def wrap_text_to_lines(draw, text, font, max_width, max_lines=2):
        words = text.split()
        lines = []
        current_line = ""
        for word in words:
            test_line = f"{current_line} {word}".strip()
            bbox = draw.textbbox((0, 0), test_line, font=font)
            w = bbox[2] - bbox[0]
            if w <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
                if len(lines) == max_lines:
                    lines[-1] = lines[-1].rstrip(".,!?;:") + "..."
                    return lines
        if current_line and len(lines) < max_lines:
            lines.append(current_line)
        elif current_line and len(lines) == max_lines:
            lines[-1] = lines[-1].rstrip(".,!?;:") + "..."
        return lines

    desc_text = str(description or "").strip()
    if desc_text:
        plot_lines = wrap_text_to_lines(draw, desc_text, desc_font, max_width=950, max_lines=2)
        y_plot = 612
        for line in plot_lines:
            draw.text((50, y_plot), line, fill='#F0F0F0', font=desc_font)
            bbox = draw.textbbox((0, 0), line, font=desc_font)
            y_plot += (bbox[3] - bbox[1]) + 8

    # --- Draw Copyright Badge in Top Right ---
    copyright_text = "@cholochhitro"
    c_bbox = draw.textbbox((0, 0), copyright_text, font=copyright_font)
    ctw = c_bbox[2] - c_bbox[0]
    cth = c_bbox[3] - c_bbox[1]

    # Capsule dimensions and placement
    pill_h = 50
    # Left margin (12) + Telegram logo diameter (30, radius 15) + Gap (12) + Text width (ctw) + Right margin (18)
    r = 15
    pill_w = 12 + (2 * r) + 12 + ctw + 18

    # Place capsule so its right edge is at x=1230
    x_start = 1230 - pill_w
    # Content area top begins at 54, so y=70 places it nicely below the top black bar with some spacing
    y_start = 70

    try:
        # 1. Crop background region for blur
        pill_box = (x_start, y_start, x_start + pill_w, y_start + pill_h)
        cropped = bg_img.crop(pill_box)

        # 2. Apply strong blur for frosted glass effect
        blurred = cropped.filter(ImageFilter.GaussianBlur(20))
        blurred = blurred.convert('RGBA')

        # 3. Apply a translucent white sheen overlay
        overlay = Image.new('RGBA', blurred.size, (255, 255, 255, 45))
        frosted = Image.alpha_composite(blurred, overlay)

        # 4. Create capsule mask
        mask = Image.new('L', (pill_w, pill_h), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle([0, 0, pill_w, pill_h], radius=pill_h // 2, fill=255)

        # 5. Composite back onto bg_img
        bg_rgba = bg_img.convert('RGBA')
        temp_layer = Image.new('RGBA', (canvas_w, canvas_h), (0, 0, 0, 0))
        temp_layer.paste(frosted, (x_start, y_start), mask)
        bg_rgba = Image.alpha_composite(bg_rgba, temp_layer)

        # 6. Draw semi-transparent white border
        border_layer = Image.new('RGBA', (canvas_w, canvas_h), (0, 0, 0, 0))
        border_draw = ImageDraw.Draw(border_layer)
        border_draw.rounded_rectangle([x_start, y_start, x_start + pill_w, y_start + pill_h], radius=pill_h // 2, outline=(255, 255, 255, 150), width=1)
        bg_rgba = Image.alpha_composite(bg_rgba, border_layer)
        bg_img = bg_rgba.convert('RGB')
        draw = ImageDraw.Draw(bg_img)
    except Exception as e:
        logger.error(f"Failed to generate frosted glass copyright badge: {e}")
        # Fallback to simple capsule without blur if anything fails
        draw.rounded_rectangle([x_start, y_start, x_start + pill_w, y_start + pill_h], radius=pill_h // 2, fill=(0, 0, 0, 150), outline='white', width=2)

    try:
        # 7. Draw Telegram logo inside the capsule
        logo_cx = x_start + 12 + r
        logo_cy = y_start + pill_h // 2
        draw_telegram_logo(draw, logo_cx, logo_cy, r)

        # 8. Draw vertically centered copyright text inside the capsule
        tx = x_start + 12 + (2 * r) + 12
        ty = y_start + (pill_h - cth) // 2 - c_bbox[1]
        # Draw text with subtle shadow first for readability on any background
        draw.text((tx + 1, ty + 1), copyright_text, fill=(0, 0, 0, 120), font=copyright_font)
        draw.text((tx, ty), copyright_text, fill=(255, 255, 255, 255), font=copyright_font)
    except Exception as e:
        logger.error(f"Failed to draw capsule contents: {e}")

    # --- Draw Small Vertical Poster (Bottom Right) ---
    px, py = 1050, 390
    pw, ph = 160, 240

    if poster_bytes:
        try:
            poster_img = Image.open(BytesIO(poster_bytes))
            poster_img = ImageOps.fit(poster_img, (pw, ph), centering=(0.5, 0.5))

            mask = Image.new('L', (pw, ph), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.rounded_rectangle([0, 0, pw, ph], radius=12, fill=255)

            temp_layer = Image.new('RGBA', (canvas_w, canvas_h), (0, 0, 0, 0))
            temp_layer.paste(poster_img.convert('RGBA'), (px, py), mask)

            bg_img = Image.alpha_composite(bg_img.convert('RGBA'), temp_layer).convert('RGB')
            draw = ImageDraw.Draw(bg_img)

            draw.rounded_rectangle([px - 2, py - 2, px + pw + 2, py + ph + 2], radius=14, outline='white', width=4)
        except Exception as e:
            logger.error(f"Failed to fetch/paste vertical poster: {e}")

    # --- Draw Widescreen Cinematic Black Bars (Top & Bottom) ---
    # Top bar: 0 to 54
    draw.rectangle([0, 0, canvas_w, 54], fill='black')
    # Bottom bar: 665 to 720 (720 - 55 = 665)
    draw.rectangle([0, 665, canvas_w, canvas_h], fill='black')

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
