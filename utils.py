import re
import os
import logging
from info import *
from imdbkit import IMDBKit 
import asyncio
from datetime import datetime
import pytz
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import InputUserDeactivated, UserNotParticipant, FloodWait, UserIsBlocked, PeerIdInvalid, ChatAdminRequired, MessageNotModified
from pyrogram import enums
from typing import Union
from Script import script
from typing import List
from database.users_chats_db import db
import requests
from shortzy import Shortzy
from plugins.poster import get_movie_detailsx

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

BTN_URL_REGEX = re.compile(
    r"(\[([^\[]+?)\]\((buttonurl|buttonalert):(?:/{0,2})(.+?)(:same)?\))"
)

imdb = IMDBKit() 
BANNED = {}
SMART_OPEN = '“'
SMART_CLOSE = '”'
START_CHAR = ('\'', '"', SMART_OPEN)

class temp(object):   
    BANNED_USERS = []
    BANNED_CHATS = []
    ME = None
    CURRENT=int(os.environ.get("SKIP", 2))
    CANCEL = False
    B_USERS_CANCEL = False
    B_GROUPS_CANCEL = False 
    MELCOW = {}
    U_NAME = None
    B_NAME = None
    B_LINK = None
    SETTINGS = {}
    GETALL = {}
    SHORT = {}
    IMDB_CAP = {}
    VERIFICATIONS = {}
    TEMP_INVITE_LINKS = {}
    REQ_LINKS = {}

def last_online(user):
    if user.is_bot:
        return "🤖 This is a bot."
    status = user.status
    if status == enums.UserStatus.ONLINE:
        return "🟢 Currently Online"
    elif status == enums.UserStatus.RECENTLY:
        return "⏳ Last seen recently"
    elif status == enums.UserStatus.LAST_WEEK:
        return "📆 Last seen within a week"
    elif status == enums.UserStatus.LAST_MONTH:
        return "📅 Last seen within a month"
    elif status == enums.UserStatus.LONG_AGO:
        return "🚫 Long ago"
    elif status == enums.UserStatus.OFFLINE:
        return f"📌 {user.last_online_date.strftime('%d %b %Y, %H:%M:%S')}"
    return "⚠️ Status unavailable"

def get_status(tz_name='Asia/Kolkata'):
    hour = datetime.now(pytz.timezone(tz_name)).hour
    return ("ɢᴏᴏᴅ ᴍᴏʀɴɪɴɢ 🌞" if 5 <= hour < 12 else
            "ɢᴏᴏᴅ ᴀꜰᴛᴇʀɴᴏᴏɴ 🌓" if hour < 17 else
            "ɢᴏᴏᴅ ᴇᴠᴇɴɪɴɢ 🌘" if hour < 21 else
            "ɢᴏᴏᴅ ɴɪɢʜᴛ 🌑")

async def stream_buttons(user_id: int, file_id: str):
     if STREAM_MODE and not PREMIUM_STREAM_MODE:
         return [
             [InlineKeyboardButton('🚀 ꜰᴀꜱᴛ ᴅᴏᴡɴʟᴏᴀᴅ / ᴡᴀᴛᴄʜ ᴏɴʟɪɴᴇ 🖥️', callback_data=f'generate_stream_link:{file_id}')],
             [InlineKeyboardButton('📜 ᴠɪᴇᴡ ᴀᴜᴅɪᴏ / ꜱᴜʙꜱ ɪɴꜰᴏ 📝', callback_data=f'extract_data:{file_id}')]
         ]
     elif STREAM_MODE and PREMIUM_STREAM_MODE:
         if not await db.has_premium_access(user_id):
             return [
                 [InlineKeyboardButton('🚀 ꜰᴀꜱᴛ ᴅᴏᴡɴʟᴏᴀᴅ / ᴡᴀᴛᴄʜ ᴏɴʟɪɴᴇ 🖥️', callback_data='prestream')],
                 [InlineKeyboardButton('📜 ᴠɪᴇᴡ ᴀᴜᴅɪᴏ / ꜱᴜʙꜱ ɪɴꜰᴏ 📝', callback_data=f'extract_data:{file_id}')]
             ]
         else:
             return [
                 [InlineKeyboardButton('🚀 ꜰᴀꜱᴛ ᴅᴏᴡɴʟᴏᴀᴅ / ᴡᴀᴛᴄʜ ᴏɴʟɪɴᴇ 🖥️', callback_data=f'generate_stream_link:{file_id}')],
                 [InlineKeyboardButton('📜 ᴠɪᴇᴡ ᴀᴜᴅɪᴏ / ꜱᴜʙꜱ ɪɴꜰᴏ 📝', callback_data=f'extract_data:{file_id}')]
             ]
     else:
         return [[InlineKeyboardButton('📌 ᴊᴏɪɴ ᴜᴘᴅᴀᴛᴇꜱ ᴄʜᴀɴɴᴇʟ 📌', url=CHANNEL_LINK)]]

async def is_req_subscribed(bot, user_id, rqfsub_channels):
    btn = []
    async def check_req_channel(ch_id):
        if await db.has_joined_channel(user_id, ch_id):
            return None
        try:
            member = await bot.get_chat_member(ch_id, user_id)
            if member.status != enums.ChatMemberStatus.BANNED:
                await db.add_join_req(user_id, ch_id)
                return None
        except UserNotParticipant:
            pass
        except Exception as e:
            logger.error(f"Error checking membership in {ch_id}: {e}")
        try:
            chat = await bot.get_chat(ch_id)
            if ch_id in temp.REQ_LINKS:
                invite_link = temp.REQ_LINKS[ch_id]
            else:
                invite = await bot.create_chat_invite_link(
                    ch_id,
                    creates_join_request=True
                )
                invite_link = invite.invite_link
                temp.REQ_LINKS[ch_id] = invite_link

            return [InlineKeyboardButton(f"⛔️ Join {chat.title}", url=invite_link)]
        except ChatAdminRequired:
            logger.warning(f"Bot not admin in {ch_id}")
        except Exception as e:
            logger.warning(f"Invite link error for {ch_id}: {e}")
        return None
    tasks = [check_req_channel(ch_id) for ch_id in rqfsub_channels]
    results = await asyncio.gather(*tasks)
    for res in results:
        if res:
            btn.append(res)
    return btn

async def is_subscribed(bot, user_id, fsub_channels):
    btn = []
    async def check_channel(channel_id):
        try:
            await bot.get_chat_member(channel_id, user_id)
        except UserNotParticipant:
            try:
                chat = await bot.get_chat(int(channel_id))
                invite_link = await bot.create_chat_invite_link(channel_id)
                return InlineKeyboardButton(f"{chat.title}", url=invite_link.invite_link)
            except Exception as e:
                logger.warning(f"Failed to create invite for {channel_id}: {e}")
        except Exception as e:
            logger.exception(f"is_subscribed error for {channel_id}: {e}")
        return None
    tasks = [check_channel(channel_id) for channel_id in fsub_channels]
    results = await asyncio.gather(*tasks)
    for button in results:
        if button:
            btn.append([button])
    return btn

async def is_check_admin(bot, chat_id, user_id):
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]
    except:
        return False
    
async def users_broadcast(user_id, message, is_pin):
    try:
        m=await message.copy(chat_id=user_id)
        if is_pin:
            try:
                await m.pin(both_sides=True)
            except Exception:
                pass
        return True, "Success"
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await users_broadcast(user_id, message, is_pin)
    except InputUserDeactivated:
        await db.delete_user(int(user_id))
        logging.info(f"{user_id}-Removed from Database, since deleted account.")
        return False, "Deleted"
    except UserIsBlocked:
        logging.info(f"{user_id} -Blocked the bot.")
        await db.delete_user(user_id)
        return False, "Blocked"
    except PeerIdInvalid:
        await db.delete_user(int(user_id))
        logging.info(f"{user_id} - PeerIdInvalid")
        return False, "Error"
    except Exception as e:
        return False, "Error"

async def groups_broadcast(chat_id, message, is_pin):
    try:
        m = await message.copy(chat_id=chat_id)
        if is_pin:
            try:
                await m.pin()
            except:
                pass
        return "Success"
    except FloodWait as e:
        await asyncio.sleep(e.x)
        return await groups_broadcast(chat_id, message)
    except Exception as e:
        await db.delete_chat(chat_id)
        return "Error"

async def junk_group(chat_id, message):
    try:
        kk = await message.copy(chat_id=chat_id)
        await kk.delete(True)
        return True, "Succes", 'mm'
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await junk_group(chat_id, message)
    except Exception as e:
        await db.delete_chat(int(chat_id))       
        logging.info(f"{chat_id} - PeerIdInvalid")
        return False, "deleted", f'{e}\n\n'

async def clear_junk(user_id, message):
    try:
        key = await message.copy(chat_id=user_id)
        await key.delete(True)
        return True, "Success"
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await clear_junk(user_id, message)
    except InputUserDeactivated:
        await db.delete_user(int(user_id))
        logging.info(f"{user_id}-Removed from Database, since deleted account.")
        return False, "Deleted"
    except UserIsBlocked:
        logging.info(f"{user_id} -Blocked the bot.")
        return False, "Blocked"
    except PeerIdInvalid:
        await db.delete_user(int(user_id))
        logging.info(f"{user_id} - PeerIdInvalid")
        return False, "Error"
    except Exception as e:
        return False, "Error"  

def listx_to_str(k):
    if k is None or k == "":
        return "N/A"
    if not hasattr(k, '__iter__') or isinstance(k, (str, int, float)):
        return str(k)
    result = []
    for elem in k:
        if elem and str(elem).strip():
            result.append(str(elem).strip())
    if MAX_LIST_ELM and len(result) > MAX_LIST_ELM:
        result = result[:int(MAX_LIST_ELM)]
    return ', '.join(result) if result else "N/A"

async def get_poster(query, bulk=False, id=False, file=None):
    if not id:
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
        'plot': plot,
        'rating': str(movie.rating),
        "url": movie.url or f"https://www.imdb.com/title/{imdb_id}"
    }

#Remove Nahi Kiya Hu.....Agar Tujha Remove Karna Hai To Kar Dena
async def old_get_poster(query, bulk=False, id=False, file=None):
    if not id:
        query = (query.strip()).lower()
        title = query
        year = re.findall(r'[1-2]\d{3}$', query, re.IGNORECASE)
        imdb
        if year:
            year = list_to_str(year[:1])
            title = (query.replace(year, "")).strip()
        elif file is not None:
            year = re.findall(r'[1-2]\d{3}', file, re.IGNORECASE)
            if year:
                year = list_to_str(year[:1]) 
        else:
            year = None
        movieid = imdb.search_movie(title.lower(), results=10)
        if not movieid:
            return None
        if year:
            filtered=list(filter(lambda k: str(k.get('year')) == str(year), movieid))
            if not filtered:
                filtered = movieid
        else:
            filtered = movieid
        movieid=list(filter(lambda k: k.get('kind') in ['movie', 'tv series'], filtered))
        if not movieid:
            movieid = filtered
        if bulk:
            return movieid
        movieid = movieid[0].movieID
    else:
        movieid = query
    movie = imdb.get_movie(movieid)
    imdb.update(movie, info=['main', 'vote details'])
    if movie.get("original air date"):
        date = movie["original air date"]
    elif movie.get("year"):
        date = movie.get("year")
    else:
        date = "N/A"
    plot = ""
    if not LONG_IMDB_DESCRIPTION:
        plot = movie.get('plot')
        if plot and len(plot) > 0:
            plot = plot[0]
    else:
        plot = movie.get('plot outline')
    if plot and len(plot) > 800:
        plot = plot[0:800] + "..."
    STANDARD_GENRES = {
        'Action', 'Adventure', 'Animation', 'Biography', 'Comedy', 'Crime', 'Documentary',
        'Drama', 'Family', 'Fantasy', 'Film-Noir', 'History', 'Horror', 'Music',
        'Musical', 'Mystery', 'Romance', 'Sci-Fi', 'Sport', 'Thriller', 'War', 'Western'
    }
    raw_genres = movie.get("genres", "N/A")
    if isinstance(raw_genres, str):
        genre_list = [g.strip() for g in raw_genres.split(",")]
        genres = ", ".join(g for g in genre_list if g in STANDARD_GENRES) or "N/A"
    else:
        genres = ", ".join(g for g in raw_genres if g in STANDARD_GENRES) or "N/A"

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
        "writer":list_to_str(movie.get("writer")),
        "producer":list_to_str(movie.get("producer")),
        "composer":list_to_str(movie.get("composer")) ,
        "cinematographer":list_to_str(movie.get("cinematographer")),
        "music_team": list_to_str(movie.get("music department")),
        "distributors": list_to_str(movie.get("distributors")),
        'release_date': date,
        'year': movie.get('year'),
        'genres': genres,
        'poster': movie.get('full-size cover url'),
        'plot': plot,
        'rating': str(movie.get("rating")),
        'url':f'https://www.imdb.com/title/tt{movieid}'
    }

async def get_posterx(query, bulk=False, id=False, file=None):
    if not id:
        details = await get_movie_detailsx(query, file=file)
    else:
        details = await get_movie_detailsx(query, id=True)

    if not details or details.get("error"):
        return None

    plot = ""
    if not LONG_IMDB_DESCRIPTION:
        plot = details.get('plot')
        if plot and len(plot) > 0:
            plot = plot[0]
    else:
        plot = details.get('plot outline')
    if plot and len(plot) > 800:
        plot = plot[0:800] + "..."
    def list_to_str(val):
        if isinstance(val, list):
            return ", ".join(str(x) for x in val if x)
        return str(val) if val else ""

    return {
        'title': details.get('title'),
        'votes': details.get('votes'),
        "aka": None,  # Not typically provided by TMDB in this format
        "seasons": details.get('seasons'),
        "box_office": details.get('box_office'),
        'localized_title': details.get('localized_title'),
        'kind': 'movie' if 'movie' in details.get('tmdb_url', '') else 'tv series',
        "imdb_id": details.get('imdb_id'),
        "cast": list_to_str(details.get("cast")),
        "runtime": list_to_str(details.get("runtime")),
        "countries": list_to_str(details.get("countries")),
        "certificates": list_to_str(details.get("certificates")),
        "languages": list_to_str(details.get("languages")),
        "director": list_to_str(details.get("director")),
        "writer": list_to_str(details.get("writer")),
        "producer": list_to_str(details.get("producer")),
        "composer": list_to_str(details.get("composer")),
        "cinematographer": list_to_str(details.get("cinematographer")),
        "music_team": None, # Not provided by the TMDB API wrapper
        "distributors": list_to_str(details.get("distributors")),
        'release_date': details.get('release_date'),
        'year': details.get('year'),
        'genres': list_to_str(details.get("genres")),
        'poster': details.get('poster_url'),
        'backdrop' : details.get('backdrop_url'),
        'plot': plot,
        'rating': str(details.get("rating", "N/A")),
        'url': details.get('tmdb_url')
    }

async def get_shortlink(link, grp_id, is_second_shortener=False, is_third_shortener=False):
    settings = await get_settings(grp_id)
    if is_third_shortener:             
        api, site = settings['api_three'], settings['shortner_three']
    else:
        if is_second_shortener:
            api, site = settings['api_two'], settings['shortner_two']
        else:
            api, site = settings['api'], settings['shortner']
    shortzy = Shortzy(api, site)
    try:
        link = await shortzy.convert(link)
    except Exception as e:
        link = await shortzy.get_quick_link(link)
    return link

async def get_settings(group_id):
    settings = temp.SETTINGS.get(group_id)
    if not settings:
        settings = await db.get_settings(group_id)
        temp.SETTINGS.update({group_id: settings})
    return settings
    
async def save_group_settings(group_id, key, value):
    current = await get_settings(group_id)
    current.update({key: value})
    temp.SETTINGS.update({group_id: current})
    await db.update_settings(group_id, current)

def clean_filename(file_name):
    prefixes = ('[', '@', 'www.')
    unwanted = {word.lower() for word in BAD_WORDS}
    
    file_name = ' '.join(
        word for word in file_name.split()
        if not (word.startswith(prefixes) or word.lower() in unwanted)
    )
    return file_name

def get_size(size):
    units = ["Bytes", "KB", "MB", "GB", "TB", "PB", "EB"]
    size = float(size)
    i = 0
    while size >= 1024.0 and i < len(units):
        i += 1
        size /= 1024.0
    return "%.2f %s" % (size, units[i])

def extract_request_content(message_text):
    match = re.search(r"<u>(.*?)</u>", message_text)
    if match:
        return match.group(1).strip()
    match = re.search(r"📝 ʀᴇǫᴜᴇꜱᴛ ?: ?(.*?)(?:\n|$)", message_text)
    if match:
        return match.group(1).strip()
    return message_text.strip()

def generate_settings_text(settings, title, reset_done=False):
    note = "\n<b>📌 ɴᴏᴛᴇ :- ʀᴇꜱᴇᴛ ꜱᴜᴄᴄᴇꜱꜱғᴜʟʟʏ ✅</b>" if reset_done else ""
    return f"""<b>⚙️ ʏᴏᴜʀ sᴇᴛᴛɪɴɢs ꜰᴏʀ - {title}</b>

✅️ <b><u>1sᴛ ᴠᴇʀɪꜰʏ sʜᴏʀᴛɴᴇʀ</u></b>
<b>ɴᴀᴍᴇ</b> - <code>{settings.get("shortner", "N/A")}</code>
<b>ᴀᴘɪ</b> - <code>{settings.get("api", "N/A")}</code>

✅️ <b><u>2ɴᴅ ᴠᴇʀɪꜰʏ sʜᴏʀᴛɴᴇʀ</u></b>
<b>ɴᴀᴍᴇ</b> - <code>{settings.get("shortner_two", "N/A")}</code>
<b>ᴀᴘɪ</b> - <code>{settings.get("api_two", "N/A")}</code>

✅️ <b><u>𝟹ʀᴅ ᴠᴇʀɪꜰʏ sʜᴏʀᴛɴᴇʀ</u></b>
<b>ɴᴀᴍᴇ</b> - <code>{settings.get("shortner_three", "N/A")}</code>
<b>ᴀᴘɪ</b> - <code>{settings.get("api_three", "N/A")}</code>

⏰ <b>2ɴᴅ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ᴛɪᴍᴇ</b> - <code>{settings.get("verify_time", "N/A")}</code>
⏰ <b>𝟹ʀᴅ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ᴛɪᴍᴇ</b> - <code>{settings.get("third_verify_time", "N/A")}</code>

1️⃣ <b>ᴛᴜᴛᴏʀɪᴀʟ ʟɪɴᴋ 1</b> - {settings.get("tutorial", TUTORIAL)}
2️⃣ <b>ᴛᴜᴛᴏʀɪᴀʟ ʟɪɴᴋ 2</b> - {settings.get("tutorial_2", TUTORIAL_2)}
3️⃣ <b>ᴛᴜᴛᴏʀɪᴀʟ ʟɪɴᴋ 3</b> - {settings.get("tutorial_3", TUTORIAL_3)}

📝 <b>ʟᴏɢ ᴄʜᴀɴɴᴇʟ ɪᴅ</b> - <code>{settings.get("log", "N/A")}</code>
🚫 <b>ꜰꜱᴜʙ ᴄʜᴀɴɴᴇʟ ɪᴅ</b> - <code>{settings.get("fsub", "N/A")}</code>


🎯 <b>ɪᴍᴅʙ ᴛᴇᴍᴘʟᴀᴛᴇ</b> - <code>{settings.get("template", "N/A")}</code>

📂 <b>ꜰɪʟᴇ ᴄᴀᴘᴛɪᴏɴ</b> - <code>{settings.get("caption", "N/A")}</code>
{note}
"""

async def group_setting_buttons(grp_id):
    settings = await get_settings(grp_id)
    buttons = [[
                InlineKeyboardButton('ʀᴇꜱᴜʟᴛ ᴘᴀɢᴇ', callback_data=f'setgs#button#{settings.get("button")}#{grp_id}',),
                InlineKeyboardButton('ʙᴜᴛᴛᴏɴ' if settings.get("button") else 'ᴛᴇxᴛ', callback_data=f'setgs#button#{settings.get("button")}#{grp_id}',),
            ],[
                InlineKeyboardButton('ꜰɪʟᴇ ꜱᴇᴄᴜʀᴇ', callback_data=f'setgs#file_secure#{settings["file_secure"]}#{grp_id}',),
                InlineKeyboardButton('✔ ᴏɴ' if settings["file_secure"] else '✘ ᴏꜰꜰ', callback_data=f'setgs#file_secure#{settings["file_secure"]}#{grp_id}',),
            ],[
                InlineKeyboardButton('ɪᴍᴅʙ ᴘᴏꜱᴛᴇʀ', callback_data=f'setgs#imdb#{settings["imdb"]}#{grp_id}',),
                InlineKeyboardButton('✔ ᴏɴ' if settings["imdb"] else '✘ ᴏꜰꜰ', callback_data=f'setgs#imdb#{settings["imdb"]}#{grp_id}',),
            ],[
                InlineKeyboardButton('ᴡᴇʟᴄᴏᴍᴇ ᴍꜱɢ', callback_data=f'setgs#welcome#{settings["welcome"]}#{grp_id}',),
                InlineKeyboardButton('✔ ᴏɴ' if settings["welcome"] else '✘ ᴏꜰꜰ', callback_data=f'setgs#welcome#{settings["welcome"]}#{grp_id}',),
            ],[
                InlineKeyboardButton('ᴀᴜᴛᴏ ᴅᴇʟᴇᴛᴇ', callback_data=f'setgs#auto_delete#{settings["auto_delete"]}#{grp_id}',),
                InlineKeyboardButton('✔ ᴏɴ' if settings["auto_delete"] else '✘ ᴏꜰꜰ', callback_data=f'setgs#auto_delete#{settings["auto_delete"]}#{grp_id}',),
            ],[
                InlineKeyboardButton('ᴍᴀx ʙᴜᴛᴛᴏɴꜱ', callback_data=f'setgs#max_btn#{settings["max_btn"]}#{grp_id}',),
                InlineKeyboardButton('10' if settings["max_btn"] else f'{MAX_BTNS}', callback_data=f'setgs#max_btn#{settings["max_btn"]}#{grp_id}',),
            ],[
                InlineKeyboardButton('ꜱᴘᴇʟʟ ᴄʜᴇᴄᴋ',callback_data=f'setgs#spell_check#{settings["spell_check"]}#{str(grp_id)}'),
                InlineKeyboardButton('✔ ᴏɴ' if settings["spell_check"] else '✘ ᴏꜰꜰ',callback_data=f'setgs#spell_check#{settings["spell_check"]}#{str(grp_id)}')
            ],[
                InlineKeyboardButton('ᴠᴇʀɪꜰʏ', callback_data=f'setgs#is_verify#{settings.get("is_verify", IS_VERIFY)}#{grp_id}'),
                InlineKeyboardButton('✔ ᴏɴ' if settings.get("is_verify", IS_VERIFY) else '✘ ᴏꜰꜰ', callback_data=f'setgs#is_verify#{settings.get("is_verify", IS_VERIFY)}#{grp_id}'),
            ],
            [
                InlineKeyboardButton("❌ ʀᴇᴍᴏᴠᴇ ❌", callback_data=f"removegrp#{grp_id}")
            ],
            [
                InlineKeyboardButton('⇋ ᴄʟᴏꜱᴇ ꜱᴇᴛᴛɪɴɢꜱ ᴍᴇɴᴜ ⇋', callback_data='close_data')
    ]]
    return buttons

def list_to_str(k):
    if not k:
        return "N/A"
    elif len(k) == 1:
        return str(k[0])
    elif MAX_LIST_ELM:
        k = k[:int(MAX_LIST_ELM)]
        return ' '.join(f'{elem}, ' for elem in k)
    else:
        return ' '.join(f'{elem}, ' for elem in k)

async def log_error(client, error_message):
    try:
        await client.send_message(
            chat_id=LOG_CHANNEL, 
            text=f"<b>⚠️ Error Log:</b>\n<code>{error_message}</code>"
        )
    except Exception as e:
        print(f"Failed to log error: {e}")

def get_time(seconds):
    periods = [(' ᴅᴀʏs', 86400), (' ʜᴏᴜʀ', 3600), (' ᴍɪɴᴜᴛᴇ', 60), (' sᴇᴄᴏɴᴅ', 1)]
    result = ''
    for period_name, period_seconds in periods:
        if seconds >= period_seconds:
            period_value, seconds = divmod(seconds, period_seconds)
            result += f'{int(period_value)}{period_name}'
    return result

def get_readable_time(seconds):
    periods = [('d', 86400), ('h', 3600), ('m', 60), ('s', 1)]
    result = []
    for period_name, period_seconds in periods:
        if seconds >= period_seconds:
            period_value, seconds = divmod(seconds, period_seconds)
            result.append(f'{int(period_value)}{period_name}')
    return ' '.join(result)  

def generate_season_variations(search_raw: str, season_number: int):
    return [
        f"{search_raw} s{season_number:02}",
        f"{search_raw} season {season_number}",
        f"{search_raw} season {season_number:02}",
    ]

async def get_seconds(time_string):
    def extract_value_and_unit(ts):
        value = ""
        unit = ""
        index = 0
        while index < len(ts) and ts[index].isdigit():
            value += ts[index]
            index += 1
        unit = ts[index:].lstrip()
        if value:
            value = int(value)
        return value, unit
    value, unit = extract_value_and_unit(time_string)
    if unit == 's':
        return value
    elif unit == 'min':
        return value * 60
    elif unit == 'hour':
        return value * 3600
    elif unit == 'day':
        return value * 86400
    elif unit == 'month':
        return value * 86400 * 30
    elif unit == 'year':
        return value * 86400 * 365
    else:
        return 0

def clean_search_text(search_raw: str) -> str:
    search_lower = search_raw.lower()
    phrases = re.split(r'\s{2,}', search_lower.strip())
    lang_pattern = r'\b(hin(di)?|eng(lish)?|mal(ayalam)?|tam(il)?|tel(ugu)?|kan(nada)?|ben(gali)?|mar(athi)?|urdu|guj(arat)?|punj(abi)?)\b'
    season_pattern = r's(eason)?\s*0*\d+'
    quality_pattern = r'\b(360p|480p|720p|1080p|1440p|2160p|4k)\b'  
    cleaned_phrases = []
    for phrase in phrases:
        phrase = re.sub(season_pattern, '', phrase, flags=re.IGNORECASE)
        phrase = re.sub(lang_pattern, '', phrase, flags=re.IGNORECASE)
        phrase = re.sub(quality_pattern, '', phrase, flags=re.IGNORECASE)
        phrase = re.sub(r'\s+', ' ', phrase).strip()
        if phrase:
            cleaned_phrases.append(phrase)
    unique_phrases = []
    seen = set()
    for cp in cleaned_phrases:
        if cp not in seen:
            unique_phrases.append(cp)
            seen.add(cp)
    if unique_phrases:
        return unique_phrases[0].title()
    else:
        return ""

async def get_cap(settings, remaining_seconds, files, query, total_results, search, offset=0):
    try:
        if settings["imdb"]:
            IMDB_CAP = temp.IMDB_CAP.get(query.from_user.id)
            if IMDB_CAP:
                cap = IMDB_CAP
                cap += "\n<b>♻️ <u>ʀᴇꜱᴜʟᴛꜱ ꜰᴏʀ ʏᴏᴜʀ sᴇᴀʀᴄʜ</u>\n\n</b>"
                for idx, file in enumerate(files, start=offset + 1):
                        cap += (
                            f"<b>{idx}. "
                            f"<a href='https://telegram.me/{temp.U_NAME}"
                            f"?start=file_{query.message.chat.id}_{file.file_id}'>"
                            f"[{get_size(file.file_size)}] "
                            f"{clean_filename(file.file_name)}\n\n"
                            f"</a></b>"
                        )
            else:
                if settings["imdb"]:
                    imdb = await get_posterx(search, file=(files[0]).file_name) if TMDB_ON_SEARCH else await get_poster(search, file=(files[0]).file_name)
                else:
                    imdb = None
                if imdb:
                    TEMPLATE = script.IMDB_TEMPLATE_TXT
                    cap = TEMPLATE.format(
                        query=search, 
                        title=imdb['title'],
                        votes=imdb['votes'],
                        aka=imdb["aka"],
                        seasons=imdb["seasons"],
                        box_office=imdb['box_office'],
                        localized_title=imdb['localized_title'],
                        kind=imdb['kind'],
                        imdb_id=imdb["imdb_id"],
                        cast=imdb["cast"],
                        runtime=imdb["runtime"],
                        countries=imdb["countries"],
                        certificates=imdb["certificates"],
                        languages=imdb["languages"],
                        director=imdb["director"],
                        writer=imdb["writer"],
                        producer=imdb["producer"],
                        composer=imdb["composer"],
                        cinematographer=imdb["cinematographer"],
                        music_team=imdb["music_team"],
                        distributors=imdb["distributors"],
                        release_date=imdb['release_date'],
                        year=imdb['year'],
                        genres=imdb['genres'],
                        poster=imdb['poster'],
                        plot=imdb['plot'],
                        rating=imdb['rating'],
                        url=imdb['url'],
                        **locals()
                    )
                    for idx, file in enumerate(files, start=offset+1):
                        cap += (
                            f"<b>{idx}. "
                            f"<a href='https://telegram.me/{temp.U_NAME}"
                            f"?start=file_{query.message.chat.id}_{file.file_id}'>"
                            f"[{get_size(file.file_size)}] "
                            f"{clean_filename(file.file_name)}\n\n"
                            f"</a></b>"
                        )
                else:
                    if FAST_MODE:
                        cap = (
                            f"<b>🙋‍♂ {query.from_user.mention}\n"
                            f"⏰ ʀᴇsᴜʟᴛ ɪɴ : <code>{remaining_seconds}</code> ꜱᴇᴄᴏɴᴅs\n</b>"
                        )
                    else:
                        cap = (
                            f"<b>🙋‍♂ {query.from_user.mention}\n"
                            f"📝 ᴛᴏᴛᴀʟ ꜰɪʟᴇꜱ : <code>{total_results}</code>\n</b>"
                        )
                    cap += "<b>\n♻️ <u>ʀᴇꜱᴜʟᴛꜱ ꜰᴏʀ ʏᴏᴜʀ sᴇᴀʀᴄʜ</u>\n\n</b>"
                    for idx, file in enumerate(files, start=offset + 1):
                        cap += (
                            f"<b>{idx}. "
                            f"<a href='https://telegram.me/{temp.U_NAME}"
                            f"?start=file_{query.message.chat.id}_{file.file_id}'>"
                            f"[{get_size(file.file_size)}] "
                            f"{clean_filename(file.file_name)}\n\n"
                            f"</a></b>"
                        )
        else:
            if FAST_MODE:
                cap = (
                    f"<b>🙋‍♂ {query.from_user.mention}\n"
                    f"⏰ ʀᴇsᴜʟᴛ ɪɴ : <code>{remaining_seconds}</code> ꜱᴇᴄᴏɴᴅs\n</b>"
                )
            else:
                cap = (
                    f"<b>🙋‍♂ {query.from_user.mention}\n"
                    f"📝 ᴛᴏᴛᴀʟ ꜰɪʟᴇꜱ : <code>{total_results}</code>\n</b>"
                )
            cap += "<b>\n♻️ <u>ʀᴇꜱᴜʟᴛꜱ ꜰᴏʀ ʏᴏᴜʀ sᴇᴀʀᴄʜ</u>\n\n</b>"
            for idx, file in enumerate(files, start=offset):
                        cap += (
                            f"<b>{idx}. "
                            f"<a href='https://telegram.me/{temp.U_NAME}"
                            f"?start=file_{query.message.chat.id}_{file.file_id}'>"
                            f"[{get_size(file.file_size)}] "
                            f"{clean_filename(file.file_name)}\n\n"
                            f"</a></b>"
                        )
        return cap
    except Exception as e:
        logging.error(f"Error in get_cap: {e}")
        pass
