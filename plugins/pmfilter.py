import asyncio
import re
import math
import random
import pytz
import logging
import tracemalloc
from info import *
from Script import script
from datetime import datetime, timedelta
from utils import get_status, get_size, is_subscribed, is_req_subscribed, group_setting_buttons, get_poster, temp, get_settings, save_group_settings, get_cap, imdb, is_check_admin, extract_request_content, log_error, clean_filename, generate_season_variations, clean_search_text, get_posterx
from fuzzywuzzy import process
from web.utils import get_name, get_hash
from urllib.parse import quote_plus
from database.ia_filterdb import Media, Media2, get_file_details, get_search_results, get_bad_files
from database.config_db import mdb
from pyrogram.errors import FloodWait, UserIsBlocked, MessageNotModified, PeerIdInvalid, ChatAdminRequired, UserNotParticipant
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, WebAppInfo, InputMediaPhoto
from pyrogram.errors.exceptions.bad_request_400 import MediaEmpty, PhotoInvalidDimensions, WebpageMediaEmpty
from database.refer import referdb
from database.users_chats_db import db

lock = asyncio.Lock()

logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)

tracemalloc.start()

BUTTON = {}
BUTTONS = {}
FRESH = {}
BUTTONS0 = {}
BUTTONS1 = {}
BUTTONS2 = {}
SPELL_CHECK = {}

@Client.on_message(filters.group & filters.text & filters.incoming & ~filters.regex(r"^/"))
async def give_filter(client, message):
    if EMOJI_MODE:
        try:
            await message.react(emoji=random.choice(REACTIONS), big=True)
        except Exception:
            await message.react(emoji="⚡️")
            pass
    if not await db.get_chat(message.chat.id):
        await db.add_chat(message.chat.id, message.chat.title)
        total=await client.get_chat_members_count(message.chat.id)
        await client.send_message(LOG_CHANNEL, script.LOG_TEXT_G.format(message.chat.title, message.chat.id, total, "Unknown"))

    await mdb.update_top_messages(message.from_user.id, message.text)
    if message.chat.id != SUPPORT_CHAT_ID:
        settings = await get_settings(message.chat.id)
        try:
            if settings['auto_filter']:
                if re.search(r'https?://\S+|www\.\S+|t\.me/\S+', message.text):
                    if await is_check_admin(client, message.chat.id, message.from_user.id):
                        return
                    return await message.delete()
                await auto_filter(client, message)
        except KeyError:
            pass

@Client.on_message(filters.private & filters.text & filters.incoming & ~filters.regex(r"^/") & ~filters.regex(r"(https?://)?(t\.me|telegram\.me|telegram\.dog)/"))
async def pm_text(bot, message):
    bot_id = bot.me.id
    content = message.text
    user = message.from_user.mention
    user_id = message.from_user.id
    if EMOJI_MODE:
        try:
            await message.react(emoji=random.choice(REACTIONS), big=True)
        except Exception:
            await message.react(emoji="⚡️")
            pass
    if not await db.is_user_exist(user_id):
        await db.add_user(user_id, message.from_user.first_name)
        await client.send_message(LOG_CHANNEL, script.LOG_TEXT_P.format(user_id, user))

    if content.startswith(("#")):
        return
    try:
        await mdb.update_top_messages(user_id, content)
        pm_search = await db.pm_search_status(bot_id)
        if pm_search:
            await auto_filter(bot, message)
        else:
            await message.reply_text(f"<b>{user},\n\n<i>ɪ ᴀᴍ ɴᴏᴛ ᴡᴏʀᴋɪɴɢ ʜᴇʀᴇ. ʏᴏᴜ ᴄᴀɴ ꜱᴇᴀʀᴄʜ ꜰɪʟᴇs ɪɴ ᴏᴜʀ ɢʀᴏᴜᴘ.</i></b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔎 ꜱᴇᴀʀᴄʜ ʜᴇʀᴇ", url=GROUP_LINK)]]))
            await bot.send_message(chat_id=LOG_CHANNEL, text=(f"<b>#ᴘᴍ_ᴍsɢ\n\n👤 ɴᴀᴍᴇ : {user}\n🆔 ɪᴅ : {user_id}\n💬 ᴍᴇssᴀɢᴇ : {content}</b>"))
    except Exception:
        pass

@Client.on_callback_query(filters.regex(r"^referral"))
async def refercall(bot, query):
    btn = [[
            InlineKeyboardButton('📩 ɪɴᴠɪᴛᴇ ʟɪɴᴋ', url=f'https://telegram.me/share/url?url=https://telegram.me/{bot.me.username}?start=reff_{query.from_user.id}&text=ʜᴇʟʟᴏ%21%20ᴇxᴘᴇʀɪᴇɴᴄᴇ%20ᴀ%20ʙᴏᴛ%20ᴛʜᴀᴛ%20ᴏꜰꜰᴇʀꜱ%20ᴀ%20ᴠᴀꜱᴛ%20ʟɪʙʀᴀʀʏ%20ᴏꜰ%20ᴜɴʟɪᴍɪᴛᴇᴅ%20ꜰɪʟᴇs.%20%F0%9F%98%83'),
            InlineKeyboardButton(f'⏳ {referdb.get_refer_points(query.from_user.id)}', callback_data='ref_point')
        ],[
            InlineKeyboardButton('⋞ ʙᴀᴄᴋ', callback_data='premium_info')
        ]]
    reply_markup = InlineKeyboardMarkup(btn)
    await query.message.edit_text(
        text=(f"ʏᴏᴜʀ ʀᴇꜰᴇʀʀᴀʟ ʟɪɴᴋ:\n\nhttps://telegram.me/{bot.me.username}?start=reff_{query.from_user.id}\n\nꜱʜᴀʀᴇ ᴛʜɪꜱ ʟɪɴᴋ ᴡɪᴛʜ ʏᴏᴜʀ ꜰʀɪᴇɴᴅꜱ.\n\n🎁 ᴇᴀᴄʜ ᴛɪᴍᴇ ᴛʜᴇʏ ᴊᴏɪɴ, ʏᴏᴜ ɢᴇᴛ 𝟷𝟶 ʀᴇꜰᴇʀʀᴀʟ ᴘᴏɪɴᴛꜱ.\n💎 ᴀꜰᴛᴇʀ 𝟷𝟶𝟶 ᴘᴏɪɴᴛꜱ, ʏᴏᴜ ɢᴇᴛ 𝟷 ᴍᴏɴᴛʜ ꜰʀᴇᴇ ᴘʀᴇᴍɪᴜᴍ ᴍᴇᴍʙᴇʀsʜɪᴘ."),
        reply_markup=reply_markup,
        parse_mode=enums.ParseMode.HTML
    )
    await query.answer()

@Client.on_callback_query(filters.regex(r"^next"))
async def next_page(bot, query):
    ident, req, key, offset = query.data.split("_")
    curr_time = datetime.now(pytz.timezone('Asia/Kolkata')).time()
    if int(req) not in [query.from_user.id, 0]:
        return await query.answer(script.ALRT_TXT.format(query.from_user.first_name), show_alert=True)
    try:
        offset = int(offset)
    except:
        offset = 0
    if BUTTONS.get(key) != None:
        search = BUTTONS.get(key)
    else:
        search = FRESH.get(key)
    if not search:
        await query.answer(script.OLD_ALRT_TXT.format(query.from_user.first_name), show_alert=True)
        return
    files, n_offset, total = await get_search_results(query.message.chat.id, search, offset=offset, filter=True)
    try:
        n_offset = int(n_offset)
    except:
        n_offset = 0

    if not files:
        return
    temp.GETALL[key] = files
    temp.SHORT[query.from_user.id] = query.message.chat.id
    settings = await get_settings(query.message.chat.id)
    if settings.get('button'):
        btn = [
            [
                InlineKeyboardButton(text=f"{get_size(file.file_size)} ≽ " + clean_filename(file.file_name), callback_data=f'file#{file.file_id}')
            ]
            for file in files
        ]
        btn.insert(0,
                   [
                       InlineKeyboardButton(f'ǫᴜᴀʟɪᴛʏ', callback_data=f"qualities#{key}"),
                       InlineKeyboardButton("ʟᴀɴɢᴜᴀɢᴇ", callback_data=f"languages#{key}"),
                       InlineKeyboardButton("sᴇᴀsᴏɴ",  callback_data=f"seasons#{key}")
                   ]
                   )
        btn.insert(0,
                   [
                       InlineKeyboardButton("📥 sᴇɴᴅ ᴀʟʟ ꜰɪʟᴇs 📥", callback_data=f"sendfiles#{key}")
                   ]
                   )

    else:
        btn = []
        btn.insert(0,
                   [
                       InlineKeyboardButton(f'ǫᴜᴀʟɪᴛʏ', callback_data=f"qualities#{key}"),
                       InlineKeyboardButton("ʟᴀɴɢᴜᴀɢᴇ", callback_data=f"languages#{key}"),
                       InlineKeyboardButton("sᴇᴀsᴏɴ",  callback_data=f"seasons#{key}")
                   ]
                   )
        btn.insert(0, [InlineKeyboardButton("📥 sᴇɴᴅ ᴀʟʟ ꜰɪʟᴇs 📥", callback_data=f"sendfiles#{key}")])
    if FAST_MODE:
        if 0 < offset <= 10:
            off_set = 0
        elif offset == 0:
            off_set = None
        else:
            off_set = offset - 10
        if n_offset == 0:
            btn.append([InlineKeyboardButton("⋞ ʙᴀᴄᴋ", callback_data=f"next_{req}_{key}_{off_set}"), InlineKeyboardButton(f"{math.ceil(int(offset)/10)+1}", callback_data="pages")])
        elif off_set is None:
            btn.append([InlineKeyboardButton(f"{math.ceil(int(offset)/10)+1}", callback_data="pages"), InlineKeyboardButton("ɴᴇxᴛ ⋟", callback_data=f"next_{req}_{key}_{n_offset}")])
        else:
            btn.append(
                [
                    InlineKeyboardButton("⋞ ʙᴀᴄᴋ", callback_data=f"next_{req}_{key}_{off_set}"),
                    InlineKeyboardButton(f"{math.ceil(int(offset)/10)+1}", callback_data="pages"),
                    InlineKeyboardButton("ɴᴇxᴛ ⋟", callback_data=f"next_{req}_{key}_{n_offset}")
                ],
            )
    else:
        try:
            if settings['max_btn']:
                if 0 < offset <= 10:
                    off_set = 0
                elif offset == 0:
                    off_set = None
                else:
                    off_set = offset - 10
                if n_offset == 0:
                    btn.append([InlineKeyboardButton("⋞ ʙᴀᴄᴋ", callback_data=f"next_{req}_{key}_{off_set}"), InlineKeyboardButton(f"{math.ceil(int(offset)/10)+1} / {math.ceil(total/10)}", callback_data="pages")])
                elif off_set is None:
                    btn.append([InlineKeyboardButton(f"{math.ceil(int(offset)/10)+1} / {math.ceil(total/10)}", callback_data="pages"), InlineKeyboardButton("ɴᴇxᴛ ⋟", callback_data=f"next_{req}_{key}_{n_offset}")])
                else:
                    btn.append(
                        [
                            InlineKeyboardButton("⋞ ʙᴀᴄᴋ", callback_data=f"next_{req}_{key}_{off_set}"),
                            InlineKeyboardButton(f"{math.ceil(int(offset)/10)+1} / {math.ceil(total/10)}", callback_data="pages"),
                            InlineKeyboardButton("ɴᴇxᴛ ⋟", callback_data=f"next_{req}_{key}_{n_offset}")
                        ],
                    )
            else:
                if 0 < offset <= int(MAX_BTNS):
                    off_set = 0
                elif offset == 0:
                    off_set = None
                else:
                    off_set = offset - int(MAX_BTNS)
                if n_offset == 0:
                    btn.append([InlineKeyboardButton("⋞ ʙᴀᴄᴋ", callback_data=f"next_{req}_{key}_{off_set}"), InlineKeyboardButton(f"{math.ceil(int(offset)/int(MAX_BTNS))+1} / {math.ceil(total/int(MAX_BTNS))}", callback_data="pages")])
                elif off_set is None:
                    btn.append([InlineKeyboardButton(f"{math.ceil(int(offset)/int(MAX_BTNS))+1} / {math.ceil(total/int(MAX_BTNS))}", callback_data="pages"), InlineKeyboardButton("ɴᴇxᴛ ⋟", callback_data=f"next_{req}_{key}_{n_offset}")])
                else:
                    btn.append(
                        [
                            InlineKeyboardButton("⋞ ʙᴀᴄᴋ", callback_data=f"next_{req}_{key}_{off_set}"),
                            InlineKeyboardButton(f"{math.ceil(int(offset)/int(MAX_BTNS))+1} / {math.ceil(total/int(MAX_BTNS))}", callback_data="pages"),
                            InlineKeyboardButton("ɴᴇxᴛ ⋟", callback_data=f"next_{req}_{key}_{n_offset}")
                        ],
                    )
        except KeyError:
            await save_group_settings(query.message.chat.id, 'max_btn', True)
            if 0 < offset <= 10:
                off_set = 0
            elif offset == 0:
                off_set = None
            else:
                off_set = offset - 10
            if n_offset == 0:
                btn.append([InlineKeyboardButton("⋞ ʙᴀᴄᴋ", callback_data=f"next_{req}_{key}_{off_set}"), InlineKeyboardButton(f"{math.ceil(int(offset)/10)+1} / {math.ceil(total/10)}", callback_data="pages")])
            elif off_set is None:
                btn.append([InlineKeyboardButton(f"{math.ceil(int(offset)/10)+1} / {math.ceil(total/10)}", callback_data="pages"), InlineKeyboardButton("ɴᴇxᴛ ⋟", callback_data=f"next_{req}_{key}_{n_offset}")])
            else:
                btn.append(
                    [
                        InlineKeyboardButton("⋞ ʙᴀᴄᴋ", callback_data=f"next_{req}_{key}_{off_set}"),
                        InlineKeyboardButton(f"{math.ceil(int(offset)/10)+1} / {math.ceil(total/10)}", callback_data="pages"),
                        InlineKeyboardButton("ɴᴇxᴛ ⋟", callback_data=f"next_{req}_{key}_{n_offset}")
                    ],
                )
    if not settings["button"]:
        cur_time = datetime.now(pytz.timezone('Asia/Kolkata')).time()
        time_difference = timedelta(hours=cur_time.hour, minutes=cur_time.minute, seconds=(cur_time.second+(cur_time.microsecond/1000000))) - \
            timedelta(hours=curr_time.hour, minutes=curr_time.minute, seconds=(
                curr_time.second+(curr_time.microsecond/1000000)))
        remaining_seconds = "{:.2f}".format(time_difference.total_seconds())
        title = clean_search_text(search)
        cap = None
        try:
            if settings['imdb']:
                cap = await get_cap(settings, remaining_seconds, files, query, total, title, offset)
                if query.message.caption:
                    try:
                        await query.message.edit_caption(caption=cap, reply_markup=InlineKeyboardMarkup(btn), parse_mode=enums.ParseMode.HTML)
                    except MessageNotModified:
                        pass
                    except Exception as e:
                        logger.exception(e)
                else:
                    try:
                        await query.message.edit_text(text=cap, reply_markup=InlineKeyboardMarkup(btn), disable_web_page_preview=True, parse_mode=enums.ParseMode.HTML)
                    except MessageNotModified:
                        pass
            else:
                cap = await get_cap(settings, remaining_seconds, files, query, total, title, offset+1)
                await query.message.edit_text(text=cap, reply_markup=InlineKeyboardMarkup(btn), disable_web_page_preview=True, parse_mode=enums.ParseMode.HTML)
        except MessageNotModified:
            pass
        except Exception as e:
            logger.exception("Failed to send result: %s", e)
    else:
        try:
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(btn))
        except MessageNotModified:
            pass
    await query.answer()

@Client.on_callback_query(filters.regex(r"^spol"))
async def advantage_spoll_choker(bot, query):
    _, id, user = query.data.split('#')
    if int(user) != 0 and query.from_user.id != int(user):
        return await query.answer(script.ALRT_TXT.format(query.from_user.first_name), show_alert=True)
    movies = await get_posterx(id, id=True) if TMDB_ON_SEARCH else await get_poster(id, id=True)
    movie = movies.get('title')
    movie = re.sub(r"[:-]", " ", movie)
    movie = re.sub(r"\s+", " ", movie).strip()
    await query.answer("ꜱᴇᴀʀᴄʜɪɴɢ ꜰᴏʀ ǫᴜᴇʀʏ ɪɴ ᴍʏ ᴅᴀᴛᴀʙᴀꜱᴇ...")
    files, offset, total_results = await get_search_results(query.message.chat.id, movie, offset=0, filter=True)
    if files:
        k = (movie, files, offset, total_results)
        await auto_filter(bot, query, k)
    else:
        reqstr1 = query.from_user.id if query.from_user else 0
        reqstr = await bot.get_users(reqstr1)
        if NO_RESULTS_MSG:
            try:
                await bot.send_message(chat_id=LOG_CHANNEL, text=script.NORSLTS.format(reqstr.id, reqstr.mention, movie))
            except Exception as e:
                print(f"Error In Spol - {e} Make Sure Bot Admin LOG CHANNEL")
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("ʀᴇǫᴜᴇsᴛ ᴛᴏ ᴀᴅᴍɪɴ 📩", user_id=int(OWNER))]])
        k = await query.message.edit(script.NOT_FOUND_TXT, reply_markup=btn)
        await asyncio.sleep(10)
        await k.delete()

@Client.on_callback_query(filters.regex(r"^qualities#"))
async def qualities_cb_handler(client: Client, query: CallbackQuery):
    try:
        if int(query.from_user.id) not in [query.message.reply_to_message.from_user.id, 0]:
            return await query.answer(script.ALRT_TXT.format(query.from_user.first_name), show_alert=True)
    except:
        pass

    _, key = query.data.split("#")
    search = FRESH.get(key)
    search = search.replace(' ', '_')

    btn = []
    for i in range(0, len(QUALITIES), 2):
        q1 = QUALITIES[i]
        row = [InlineKeyboardButton(
            text=q1, callback_data=f"fq#{q1.lower()}#{key}")]
        if i + 1 < len(QUALITIES):
            q2 = QUALITIES[i + 1]
            row.append(InlineKeyboardButton(
                text=q2, callback_data=f"fq#{q2.lower()}#{key}"))
        btn.append(row)

    btn.insert(0, [InlineKeyboardButton(text="⇊ ꜱᴇʟᴇᴄᴛ ǫᴜᴀʟɪᴛʏ ⇊", callback_data="ident")])
    btn.append([InlineKeyboardButton(text="⋞ ʙᴀᴄᴋ ᴛᴏ ꜰɪʟᴇs", callback_data=f"fq#homepage#{key}")])
    await query.edit_message_reply_markup(InlineKeyboardMarkup(btn))

@Client.on_callback_query(filters.regex(r"^fq#"))
async def filter_qualities_cb_handler(client: Client, query: CallbackQuery):
    _, qual, key = query.data.split("#")
    is_premium = await db.has_premium_access(query.from_user.id)
    if qual != "homepage":
        if QUALITY_LIMIT:
            if not is_premium and qual not in FREE_QUALITIES:
                return await query.answer("ᴛʜɪs ǫᴜᴀʟɪᴛʏ ɪs ꜰᴏʀ ᴘʀᴇᴍɪᴜᴍ ᴜsᴇʀs ᴏɴʟʏ !", show_alert=True)
    curr_time = datetime.now(pytz.timezone('Asia/Kolkata')).time()
    search = FRESH.get(key)
    search = search.replace("_", " ")
    baal = qual in search
    if baal:
        search = search.replace(qual, "")
    else:
        search = search
    req = query.from_user.id
    chat_id = query.message.chat.id
    message = query.message
    try:
        if int(query.from_user.id) not in [query.message.reply_to_message.from_user.id, 0]:
            return await query.answer(script.ALRT_TXT.format(query.from_user.first_name), show_alert=True)
    except:
        pass
    if qual != "homepage":
        search = f"{search} {qual}"
    BUTTONS[key] = search
    files, offset, total_results = await get_search_results(chat_id, search, offset=0, filter=True)
    if not files:
        await query.answer("🚫 ɴᴏ ꜰɪʟᴇꜱ ᴡᴇʀᴇ ꜰᴏᴜɴᴅ 🚫", show_alert=True)
        return
    temp.GETALL[key] = files
    settings = await get_settings(message.chat.id)
    if settings.get('button'):
        btn = [
            [
                InlineKeyboardButton(text=f"{get_size(file.file_size)} ≽ " + clean_filename(file.file_name), callback_data=f'file#{file.file_id}')
            ]
            for file in files
        ]
        btn.insert(0,
                   [
                       InlineKeyboardButton(f'ǫᴜᴀʟɪᴛʏ', callback_data=f"qualities#{key}"),
                       InlineKeyboardButton("ʟᴀɴɢᴜᴀɢᴇ", callback_data=f"languages#{key}"),
                       InlineKeyboardButton("sᴇᴀsᴏɴ",  callback_data=f"seasons#{key}")
                   ]
                   )
        btn.insert(0,
                   [
                       InlineKeyboardButton("📥 sᴇɴᴅ ᴀʟʟ ꜰɪʟᴇs 📥", callback_data=f"sendfiles#{key}")
                   ])
    else:
        btn = []
        btn.insert(0,
                   [
                       InlineKeyboardButton(f'ǫᴜᴀʟɪᴛʏ', callback_data=f"qualities#{key}"),
                       InlineKeyboardButton("ʟᴀɴɢᴜᴀɢᴇ", callback_data=f"languages#{key}"),
                       InlineKeyboardButton("sᴇᴀsᴏɴ",  callback_data=f"seasons#{key}")
                   ]
                   )
        btn.insert(0,
                   [
                       InlineKeyboardButton("📥 sᴇɴᴅ ᴀʟʟ ꜰɪʟᴇs 📥", callback_data=f"sendfiles#{key}")
                   ])
    if offset != "":
        try:
            if settings['max_btn']:
                btn.append([InlineKeyboardButton(text=f"1/{math.ceil(int(total_results)/10)}", callback_data="pages"), InlineKeyboardButton(text="ɴᴇxᴛ ⋟", callback_data=f"next_{req}_{key}_{offset}")])
            else:
                btn.append([InlineKeyboardButton(text=f"1/{math.ceil(int(total_results)/int(MAX_BTNS))}", callback_data="pages"), InlineKeyboardButton(text="ɴᴇxᴛ ⋟", callback_data=f"next_{req}_{key}_{offset}")])
        except KeyError:
            await save_group_settings(query.message.chat.id, 'max_btn', True)
            btn.append([InlineKeyboardButton(text=f"1/{math.ceil(int(total_results)/10)}", callback_data="pages"), InlineKeyboardButton(text="ɴᴇxᴛ ⋟", callback_data=f"next_{req}_{key}_{offset}")])
    else:
        btn.append([InlineKeyboardButton(text="🚸 ɴᴏ ᴍᴏʀᴇ ᴘᴀɢᴇs 🚸", callback_data="pages")])

    if not settings["button"]:
        cur_time = datetime.now(pytz.timezone('Asia/Kolkata')).time()
        time_difference = timedelta(hours=cur_time.hour, minutes=cur_time.minute, seconds=(cur_time.second+(cur_time.microsecond/1000000))) - \
            timedelta(hours=curr_time.hour, minutes=curr_time.minute, seconds=(
                curr_time.second+(curr_time.microsecond/1000000)))
        remaining_seconds = "{:.2f}".format(time_difference.total_seconds())
        title = clean_search_text(search)
        cap = await get_cap(settings, remaining_seconds, files, query, total_results, title, offset=1)
        try:
            await query.message.edit_text(text=cap, reply_markup=InlineKeyboardMarkup(btn), disable_web_page_preview=True, parse_mode=enums.ParseMode.HTML)
        except MessageNotModified:
            pass
    else:
        try:
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(btn))
        except MessageNotModified:
            pass
    await query.answer()

@Client.on_callback_query(filters.regex(r"^languages#"))
async def languages_cb_handler(client: Client, query: CallbackQuery):
    try:
        if int(query.from_user.id) not in [query.message.reply_to_message.from_user.id, 0]:
            return await query.answer(script.ALRT_TXT.format(query.from_user.first_name), show_alert=True)
    except:
        pass

    _, key = query.data.split("#")
    search = FRESH.get(key)
    search = search.replace(' ', '_')

    items = list(LANGUAGES.items())
    btn = []

    for i in range(0, len(items), 2):
        name1, code1 = items[i]
        row = [InlineKeyboardButton(
            text=name1, callback_data=f"fl#{code1}#{key}")]
        if i + 1 < len(items):
            name2, code2 = items[i + 1]
            row.append(InlineKeyboardButton(
                text=name2, callback_data=f"fl#{code2}#{key}"))
        btn.append(row)

    btn.insert(0, [InlineKeyboardButton(text="⇊ ꜱᴇʟᴇᴄᴛ ʟᴀɴɢᴜᴀɢᴇ ⇊", callback_data="ident")])
    btn.append([InlineKeyboardButton(text="⋞ ʙᴀᴄᴋ ᴛᴏ ꜰɪʟᴇs", callback_data=f"fl#homepage#{key}")])
    await query.edit_message_reply_markup(InlineKeyboardMarkup(btn))

@Client.on_callback_query(filters.regex(r"^fl#"))
async def filter_languages_cb_handler(client: Client, query: CallbackQuery):
    _, lang, key = query.data.split("#")
    curr_time = datetime.now(pytz.timezone('Asia/Kolkata')).time()
    search = FRESH.get(key)
    search = search.replace("_", " ")
    baal = lang in search
    if baal:
        search = search.replace(lang, "")
    else:
        search = search
    req = query.from_user.id
    chat_id = query.message.chat.id
    message = query.message
    try:
        if int(query.from_user.id) not in [query.message.reply_to_message.from_user.id, 0]:
            return await query.answer(script.ALRT_TXT.format(query.from_user.first_name), show_alert=True,)
    except:
        pass
    if lang != "homepage":
        search = f"{search} {lang}"
    BUTTONS[key] = search
    files, offset, total_results = await get_search_results(chat_id, search, offset=0, filter=True)
    if not files:
        await query.answer("🚫 ɴᴏ ꜰɪʟᴇꜱ ᴡᴇʀᴇ ꜰᴏᴜɴᴅ 🚫", show_alert=1)
        return
    temp.GETALL[key] = files
    settings = await get_settings(message.chat.id)
    if settings.get('button'):
        btn = [
            [
                InlineKeyboardButton(text=f"{get_size(file.file_size)} ≽ " + clean_filename(file.file_name), callback_data=f'file#{file.file_id}')
            ]
            for file in files
        ]
        btn.insert(0,
                   [
                       InlineKeyboardButton(f'ǫᴜᴀʟɪᴛʏ', callback_data=f"qualities#{key}"),
                       InlineKeyboardButton("ʟᴀɴɢᴜᴀɢᴇ", callback_data=f"languages#{key}"),
                       InlineKeyboardButton("sᴇᴀsᴏɴ",  callback_data=f"seasons#{key}")
                   ]
                   )
        btn.insert(0,
                   [
                       InlineKeyboardButton("📥 sᴇɴᴅ ᴀʟʟ ꜰɪʟᴇs 📥", callback_data=f"sendfiles#{key}")
                   ]
                   )
    else:
        btn = []
        btn.insert(0,
                   [
                       InlineKeyboardButton(f'ǫᴜᴀʟɪᴛʏ', callback_data=f"qualities#{key}"),
                       InlineKeyboardButton("ʟᴀɴɢᴜᴀɢᴇ", callback_data=f"languages#{key}"),
                       InlineKeyboardButton("sᴇᴀsᴏɴ",  callback_data=f"seasons#{key}")
                   ])
        btn.insert(0,
                   [
                       InlineKeyboardButton("📥 sᴇɴᴅ ᴀʟʟ ꜰɪʟᴇs 📥", callback_data=f"sendfiles#{key}")
                   ])
    if offset != "":
        try:
            if settings['max_btn']:
                btn.append([InlineKeyboardButton(text=f"1/{math.ceil(int(total_results)/10)}", callback_data="pages"), InlineKeyboardButton(text="ɴᴇxᴛ ⋟", callback_data=f"next_{req}_{key}_{offset}")])
            else:
                btn.append([InlineKeyboardButton(text=f"1/{math.ceil(int(total_results)/int(MAX_BTNS))}", callback_data="pages"), InlineKeyboardButton(text="ɴᴇxᴛ ⋟", callback_data=f"next_{req}_{key}_{offset}")])
        except KeyError:
            await save_group_settings(query.message.chat.id, 'max_btn', True)
            btn.append([InlineKeyboardButton(text=f"1/{math.ceil(int(total_results)/10)}", callback_data="pages"), InlineKeyboardButton(text="ɴᴇxᴛ ⋟", callback_data=f"next_{req}_{key}_{offset}")])
    else:
        btn.append([InlineKeyboardButton(text="🚸 ɴᴏ ᴍᴏʀᴇ ᴘᴀɢᴇs 🚸", callback_data="pages")])
    if not settings["button"]:
        cur_time = datetime.now(pytz.timezone('Asia/Kolkata')).time()
        time_difference = timedelta(hours=cur_time.hour, minutes=cur_time.minute, seconds=(cur_time.second+(cur_time.microsecond/1000000))) - \
            timedelta(hours=curr_time.hour, minutes=curr_time.minute, seconds=(
                curr_time.second+(curr_time.microsecond/1000000)))
        remaining_seconds = "{:.2f}".format(time_difference.total_seconds())
        title = clean_search_text(search)
        cap = await get_cap(settings, remaining_seconds, files, query, total_results, title, offset=1)
        try:
            await query.message.edit_text(text=cap, reply_markup=InlineKeyboardMarkup(btn), disable_web_page_preview=True, parse_mode=enums.ParseMode.HTML)
        except MessageNotModified:
            pass
    else:
        try:
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(btn))
        except MessageNotModified:
            pass
    await query.answer()

@Client.on_callback_query(filters.regex(r"^seasons#"))
async def seasons_cb_handler(client: Client, query: CallbackQuery):
    try:
        if int(query.from_user.id) not in [query.message.reply_to_message.from_user.id, 0]:
            return await query.answer(script.ALRT_TXT.format(query.from_user.first_name), show_alert=True)
    except Exception:
        pass
    _, key = query.data.split("#")
    search = FRESH.get(key).replace(" ", "_")
    req = query.from_user.id
    offset = 0
    btn: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(SEASONS) - 1, 2):
        btn.append([
            InlineKeyboardButton(f"sᴇᴀꜱᴏɴ {SEASONS[i][1:]}", callback_data=f"fs#{SEASONS[i].lower()}#{key}"),
            InlineKeyboardButton(f"sᴇᴀꜱᴏɴ {SEASONS[i+1][1:]}", callback_data=f"fs#{SEASONS[i+1].lower()}#{key}")
        ])

    btn.insert(
        0,
        [InlineKeyboardButton("⇊ ꜱᴇʟᴇᴄᴛ ꜱᴇᴀꜱᴏɴ ⇊", callback_data="ident")],
    )
    btn.append([InlineKeyboardButton(text="⋞ ʙᴀᴄᴋ ᴛᴏ ꜰɪʟᴇs", callback_data=f"next_{req}_{key}_{offset}")])
    await query.edit_message_reply_markup(InlineKeyboardMarkup(btn))
    await query.answer()

@Client.on_callback_query(filters.regex(r"^fs#"))
async def filter_seasons_cb_handler(client: Client, query: CallbackQuery):
    _, season_tag, key = query.data.split("#")
    search = FRESH.get(key).replace("_", " ")
    season_tag = season_tag.lower()
    if season_tag == "homepage":
        search_final = search
        query_input = search_final
    else:
        season_number = int(season_tag[1:])
        query_input = generate_season_variations(search, season_number)
        search_final = query_input[0] if query_input else search

    BUTTONS[key] = search_final
    try:
        if int(query.from_user.id) not in [query.message.reply_to_message.from_user.id, 0]:
            return await query.answer("⚠️ ɴᴏᴛ ʏᴏᴜʀ ʀᴇǫᴜᴇsᴛ", show_alert=True)
    except Exception:
        pass

    chat_id = query.message.chat.id
    req = query.from_user.id
    files, n_offset, total_results = await get_search_results(chat_id, query_input, offset=0, filter=True)
    if not files:
        BUTTONS[key] = None
        return await query.answer("🚫 ɴᴏ ꜰɪʟᴇꜱ ꜰᴏᴜɴᴅ 🚫", show_alert=True)

    temp.GETALL[key] = files
    settings = await get_settings(chat_id)
    btn: list[list[InlineKeyboardButton]] = []
    if settings.get("button"):
        btn.extend(
            [
                [
                    InlineKeyboardButton(text=f"{get_size(f.file_size)} ≽ " + clean_filename(f.file_name), callback_data=f"file#{f.file_id}")
                ]
                for f in files
            ]
        )
    btn.insert(
        0,
        [
            InlineKeyboardButton("ǫᴜᴀʟɪᴛʏ", callback_data=f"qualities#{key}"),
            InlineKeyboardButton("ʟᴀɴɢᴜᴀɢᴇ", callback_data=f"languages#{key}"),
            InlineKeyboardButton("sᴇᴀsᴏɴ", callback_data=f"seasons#{key}"),
        ],
    )
    btn.insert(
        0,
        [
            InlineKeyboardButton("📥 sᴇɴᴅ ᴀʟʟ ꜰɪʟᴇs 📥", callback_data=f"sendfiles#{key}"),
        ],
    )
    if n_offset != "":
        try:
            if settings['max_btn']:
                btn.append([InlineKeyboardButton(text=f"1/{math.ceil(int(total_results)/10)}", callback_data="pages"), InlineKeyboardButton(text="ɴᴇxᴛ ⋟", callback_data=f"next_{req}_{key}_{n_offset}")])
            else:
                btn.append([InlineKeyboardButton(text=f"1/{math.ceil(int(total_results)/int(MAX_BTNS))}", callback_data="pages"), InlineKeyboardButton(text="ɴᴇxᴛ ⋟", callback_data=f"next_{req}_{key}_{n_offset}")])
        except KeyError:
            await save_group_settings(query.message.chat.id, 'max_btn', True)
            btn.append([InlineKeyboardButton(text=f"1/{math.ceil(int(total_results)/10)}", callback_data="pages"), InlineKeyboardButton(text="ɴᴇxᴛ ⋟", callback_data=f"next_{req}_{key}_{n_offset}")])
    else:
        n_offset = 0
        btn.append([InlineKeyboardButton("🚸 ɴᴏ ᴍᴏʀᴇ ᴘᴀɢᴇs 🚸", callback_data="pages")])

    if not settings.get("button"):
        curr_time = datetime.now(pytz.timezone("Asia/Kolkata")).time()
        time_difference = timedelta(
            hours=curr_time.hour,
            minutes=curr_time.minute,
            seconds=curr_time.second + curr_time.microsecond / 1_000_000,
        )
        remaining_seconds = f"{time_difference.total_seconds():.2f}"
        title = clean_search_text(search_final)
        cap = await get_cap(settings, remaining_seconds, files, query, total_results, title, offset=1)
        try:
            await query.message.edit_text(
                text=cap,
                reply_markup=InlineKeyboardMarkup(btn),
                disable_web_page_preview=True,
            )
        except MessageNotModified:
            pass
    else:
        try:
            await query.edit_message_reply_markup(InlineKeyboardMarkup(btn))
        except MessageNotModified:
            pass
    await query.answer()

@Client.on_callback_query(group=10)
async def cb_handler(client: Client, query: CallbackQuery):
    TechifyBots = query.data
    try:
        link = await client.create_chat_invite_link(int(REQST_CHANNEL))
    except:
        pass
        return
        return
    if query.data == "close_data":
        try:
            user = query.message.reply_to_message.from_user.id
        except:
            user = query.from_user.id
        if int(user) != 0 and query.from_user.id != int(user):
            return await query.answer("ᴀᴄᴄᴇꜱꜱ ᴅᴇɴɪᴇᴅ ⚠️", show_alert=True)
        await query.answer("ᴛʜᴀɴᴋs ꜰᴏʀ ᴄʟᴏsᴇ 🙈")
        await query.message.delete()
        try:
            await query.message.reply_to_message.delete()
        except:
            pass
            return
        return

    elif query.data == "pages":
        await query.answer("ᴛʜɪs ɪs ᴘᴀɢᴇs ʙᴜᴛᴛᴏɴ 😅")
        return
        return

    if query.data.startswith("file"):
        ident, file_id = query.data.split("#")
        user = query.message.reply_to_message.from_user.id if query.message.reply_to_message else query.from_user.id
        if int(user) != 0 and query.from_user.id != int(user):
            return await query.answer(script.ALRT_TXT.format(query.from_user.first_name), show_alert=True)
        await query.answer(url=f"https://telegram.me/{temp.U_NAME}?start=file_{query.message.chat.id}_{file_id}")
        return
        return

    elif query.data.startswith("sendfiles"):
        clicked = query.from_user.id
        ident, key = query.data.split("#")

        if not await db.has_premium_access(clicked):
            await query.answer("ᴛʜɪs ꜰᴇᴀᴛᴜʀᴇ ɪs ᴏɴʟʏ ᴀᴠᴀɪʟᴀʙʟᴇ ᴛᴏ ᴘʀᴇᴍɪᴜᴍ ᴜsᴇʀs.", show_alert=True)
            return

        settings = await get_settings(query.message.chat.id)
        try:
            await query.answer(url=f"https://telegram.me/{temp.U_NAME}?start=allfiles_{query.message.chat.id}_{key}")
            return
        except UserIsBlocked:
            await query.answer("ᴜɴʙʟᴏᴄᴋ ᴛʜᴇ ʙᴏᴛ !", show_alert=True)
        except PeerIdInvalid:
            await query.answer(url=f"https://telegram.me/{temp.U_NAME}?start=sendfiles3_{key}")
        except Exception as e:
            logger.exception(e)
            await query.answer(url=f"https://telegram.me/{temp.U_NAME}?start=sendfiles4_{key}")
            return
        return

    elif query.data.startswith("autofilter_delete"):
        await Media.collection.drop()
        if MULTIPLE_DB:    
            await Media2.collection.drop()
        await query.answer("ᴇᴠᴇʀʏᴛʜɪɴɢ'ꜱ ɢᴏɴᴇ")
        await query.message.edit('ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ ᴀʟʟ ɪɴᴅᴇxᴇᴅ ꜰɪʟᴇꜱ ✅')
        return
        return

    elif query.data.startswith("checksub"):
        try:
            ident, kk, file_id = query.data.split("#")
            btn = []
            chat = file_id.split("_")[0]
            settings = await get_settings(chat)
            fsub_channels = list(dict.fromkeys((settings.get('fsub', []) if settings else [])+ AUTH_CHANNELS)) 
            btn += await is_subscribed(client, query.from_user.id, fsub_channels)
            btn += await is_req_subscribed(client, query.from_user.id, AUTH_REQ_CHANNELS)
            if btn:
                btn.append([InlineKeyboardButton("♻️ ᴛʀʏ ᴀɢᴀɪɴ ♻️", callback_data=f"checksub#{kk}#{file_id}")])
                try:
                    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(btn))
                except MessageNotModified:
                    pass
                await query.answer("🛑 ᴊᴏɪɴ ᴀʟʟ ᴜᴘᴅᴀᴛᴇ ᴄʜᴀɴɴᴇʟs ⚠️", show_alert=True)
                return
            await query.answer(url=f"https://telegram.me/{temp.U_NAME}?start={kk}_{file_id}")
            await query.message.delete()
        except Exception as e:
            await log_error(client, f"❌ Error in checksub callback:\n\n{repr(e)}")
            logger.error(f"❌ Error in checksub callback:\n\n{repr(e)}")
            return
        return

    elif query.data.startswith("killfilesdq"):
        ident, keyword = query.data.split("#")
        await query.message.edit_text(f"<b>ꜰᴇᴛᴄʜɪɴɢ ꜰɪʟᴇs ꜰᴏʀ ʏᴏᴜʀ ǫᴜᴇʀʏ {keyword}</b>")
        files, total = await get_bad_files(keyword)
        await query.message.edit_text("<b>ꜰɪʟᴇ ᴅᴇʟᴇᴛɪᴏɴ ᴘʀᴏᴄᴇꜱꜱ ᴡɪʟʟ ꜱᴛᴀʀᴛ ɪɴ 𝟻 ꜱᴇᴄᴏɴᴅꜱ !</b>")
        await asyncio.sleep(5)
        deleted = 0
        async with lock:
            try:
                for file in files:
                    file_ids = file.file_id
                    file_name = file.file_name
                    result = await Media.collection.delete_one({
                        '_id': file_ids,
                    })
                    if not result.deleted_count and MULTIPLE_DB:
                        result = await Media2.collection.delete_one({
                            '_id': file_ids,
                        })
                    if result.deleted_count:
                        logger.info(
                            f'ꜰɪʟᴇ ꜰᴏᴜɴᴅ ꜰᴏʀ ʏᴏᴜʀ ǫᴜᴇʀʏ {keyword}! ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ {file_name} ꜰʀᴏᴍ ᴅᴀᴛᴀʙᴀꜱᴇ.')
                    deleted += 1
                    if deleted % 20 == 0:
                        await query.message.edit_text(f"<b>ᴘʀᴏᴄᴇꜱꜱ ꜱᴛᴀʀᴛᴇᴅ ꜰᴏʀ ᴅᴇʟᴇᴛɪɴɢ ꜰɪʟᴇꜱ ꜰʀᴏᴍ ᴅʙ. ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ {str(deleted)} ꜰɪʟᴇꜱ ꜰʀᴏᴍ ᴅʙ ꜰᴏʀ ʏᴏᴜʀ ǫᴜᴇʀʏ {keyword} !\n\nᴘʟᴇᴀꜱᴇ ᴡᴀɪᴛ...</b>")
            except Exception as e:
                print(f"Error In killfiledq -{e}")
                await query.message.edit_text(f'Error: {e}')
            else:
                await query.message.edit_text(f"<b>ᴘʀᴏᴄᴇꜱꜱ ᴄᴏᴍᴘʟᴇᴛᴇᴅ ꜰᴏʀ ꜰɪʟᴇ ᴅᴇʟᴇᴛᴀᴛɪᴏɴ !\n\nꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ {str(deleted)} ꜰɪʟᴇꜱ ꜰʀᴏᴍ ᴅʙ ꜰᴏʀ ʏᴏᴜʀ ǫᴜᴇʀʏ {keyword}.</b>")
                return
        return

    elif query.data.startswith("opnsetgrp"):
        ident, grp_id = query.data.split("#")
        userid = query.from_user.id if query.from_user else None
        st = await client.get_chat_member(grp_id, userid)
        if (
                st.status != enums.ChatMemberStatus.ADMINISTRATOR
                and st.status != enums.ChatMemberStatus.OWNER
                and str(userid) not in ADMINS
        ):
            await query.answer("ʏᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ʀɪɢʜᴛꜱ ᴛᴏ ᴅᴏ ᴛʜɪꜱ !", show_alert=True)
            return
        title = query.message.chat.title
        settings = await get_settings(grp_id)
        if settings is not None:
            buttons = await group_setting_buttons(int(grp_id))
            reply_markup = InlineKeyboardMarkup(buttons)
            await query.message.edit_text(
                text=f"<b>ᴄʜᴀɴɢᴇ ʏᴏᴜʀ ꜱᴇᴛᴛɪɴɢꜱ ꜰᴏʀ {title} ᴀꜱ ʏᴏᴜ ᴡɪꜱʜ ⚙</b>",
                disable_web_page_preview=True,
                parse_mode=enums.ParseMode.HTML
            )
            await query.message.edit_reply_markup(reply_markup)
            return
        return

    elif query.data.startswith("opnsetpm"):
        ident, grp_id = query.data.split("#")
        userid = query.from_user.id if query.from_user else None
        st = await client.get_chat_member(grp_id, userid)
        if (
                st.status != enums.ChatMemberStatus.ADMINISTRATOR
                and st.status != enums.ChatMemberStatus.OWNER
                and str(userid) not in ADMINS
        ):
            await query.answer("ʏᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ sᴜꜰꜰɪᴄɪᴀɴᴛ ʀɪɢʜᴛs ᴛᴏ ᴅᴏ ᴛʜɪs !", show_alert=True)
            return
        title = query.message.chat.title
        settings = await get_settings(grp_id)
        await query.message.edit_text(f"<b>ʏᴏᴜʀ sᴇᴛᴛɪɴɢs ᴍᴇɴᴜ ꜰᴏʀ {title} ʜᴀs ʙᴇᴇɴ sᴇɴᴛ ᴛᴏ ʏᴏᴜ ʙʏ ᴅᴍ.</b>")
        await query.message.edit_reply_markup(InlineKeyboardMarkup([[InlineKeyboardButton("ᴄʜᴇᴄᴋ ᴍʏ ᴅᴍ 🗳️", url=f"telegram.me/{temp.U_NAME}")]]))
        if settings is not None:
            buttons = await group_setting_buttons(int(grp_id))
            reply_markup = InlineKeyboardMarkup(buttons)
            await client.send_message(
                chat_id=userid,
                text=f"<b>ᴄʜᴀɴɢᴇ ʏᴏᴜʀ ꜱᴇᴛᴛɪɴɢꜱ ꜰᴏʀ {title} ᴀꜱ ʏᴏᴜ ᴡɪꜱʜ ⚙</b>",
                reply_markup=reply_markup,
                disable_web_page_preview=True,
                parse_mode=enums.ParseMode.HTML,
                reply_to_message_id=query.message.id
            )
            return
        return

    elif query.data.startswith("show_option"):
        ident, from_user = query.data.split("#")
        btn = [[
            InlineKeyboardButton("🟢 ᴜᴘʟᴏᴀᴅᴇᴅ", callback_data=f"uploaded#{from_user}"),
            InlineKeyboardButton("⚠️ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ", callback_data=f"unavailable#{from_user}")
        ], [
            InlineKeyboardButton("🛑 ɴᴏᴛ ʀᴇʟᴇᴀsᴇᴅ", callback_data=f"Not_Released#{from_user}"),
            InlineKeyboardButton("♻️ ᴀʟʀᴇᴀᴅʏ ᴀᴠᴀɪʟᴀʙʟᴇ", callback_data=f"already_available#{from_user}")
        ], [
            InlineKeyboardButton("🚫 ᴏꜰꜰ-ᴛᴏᴘɪᴄ", callback_data=f"offtopic#{from_user}"),
            InlineKeyboardButton("📝 ᴡʀᴏɴɢ sᴘᴇʟʟɪɴɢ", callback_data=f"Wrong_Spelling#{from_user}")
        ], [
            InlineKeyboardButton("✨ ɴᴏᴛ ᴀᴠᴀɪʟᴀʙʟᴇ ɪɴ ʜɪɴᴅɪ ✨", callback_data=f"Not_Available_In_Hindi#{from_user}")
        ]]
        if query.from_user.id in ADMINS:
            user = await client.get_users(from_user)
            reply_markup = InlineKeyboardMarkup(btn)
            await query.message.edit_reply_markup(reply_markup)
            await query.answer("ᴀᴠᴀɪʟᴀʙʟᴇ ᴏᴘᴛɪᴏɴs")
        else:
            await query.answer("ᴀᴄᴄᴇss ᴅᴇɴɪᴇᴅ !", show_alert=True)
            return
        return

    elif query.data.startswith("uploaded"):
        ident, from_user = query.data.split("#")
        btn = [[
            InlineKeyboardButton("🟢 ᴜᴘʟᴏᴀᴅᴇᴅ 🟢", callback_data=f"upalert#{from_user}")
        ]]
        btn2 = [[
            InlineKeyboardButton('ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟ', url=link.invite_link),
            InlineKeyboardButton("ᴠɪᴇᴡ ꜱᴛᴀᴛᴜꜱ", url=f"{query.message.link}")
        ], [
            InlineKeyboardButton("ꜱᴇᴀʀᴄʜ ʜᴇʀᴇ", url=GROUP_LINK)
        ]]
        if query.from_user.id in ADMINS:
            user = await client.get_users(from_user)
            reply_markup = InlineKeyboardMarkup(btn)
            content = query.message.text
            await query.message.edit_text(f"<b><strike>{content}</strike></b>")
            await query.message.edit_reply_markup(reply_markup)
            await query.answer("sᴇᴛ ᴛᴏ ᴜᴘʟᴏᴀᴅᴇᴅ !")
            content = extract_request_content(query.message.text)
            try:
                await client.send_message(
                    chat_id=int(from_user),
                    text=f"<b>{user.mention},\n\n<u>{content}</u> ʏᴏᴜʀ ʀᴇǫᴜᴇꜱᴛ ʜᴀꜱ ʙᴇᴇɴ ᴜᴘʟᴏᴀᴅᴇᴅ ʙʏ ᴏᴜʀ ᴍᴏᴅᴇʀᴀᴛᴏʀs.\nᴋɪɴᴅʟʏ sᴇᴀʀᴄʜ ɪɴ ᴏᴜʀ ɢʀᴏᴜᴘ.\n\n#ᴜᴘʟᴏᴀᴅᴇᴅ ✅</b>",
                    reply_markup=InlineKeyboardMarkup(btn2))
            except UserIsBlocked:
                pass
        else:
            await query.answer("ᴀᴄᴄᴇss ᴅᴇɴɪᴇᴅ !", show_alert=True)
            return
        return

    elif query.data.startswith("upalert"):
        ident, from_user = query.data.split("#")
        if int(query.from_user.id) == int(from_user):
            user = await client.get_users(from_user)
            await query.answer(f"{user.first_name},\n\nʏᴏᴜʀ ʀᴇǫᴜᴇꜱᴛ ɪꜱ ᴜᴘʟᴏᴀᴅᴇᴅ.", show_alert=True)
        else:
            await query.answer("ᴀᴄᴄᴇss ᴅᴇɴɪᴇᴅ !", show_alert=True)
            return
        return

    elif query.data.startswith("unavailable"):
        ident, from_user = query.data.split("#")
        btn = [
            [InlineKeyboardButton("⚠️ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ ⚠️", callback_data=f"unalert#{from_user}")]
        ]
        btn2 = [
            [InlineKeyboardButton('ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟ', url=link.invite_link),
             InlineKeyboardButton("ᴠɪᴇᴡ ꜱᴛᴀᴛᴜꜱ", url=f"{query.message.link}")]
        ]
        if query.from_user.id in ADMINS:
            user = await client.get_users(from_user)
            reply_markup = InlineKeyboardMarkup(btn)
            content = query.message.text
            await query.message.edit_text(f"<b><strike>{content}</strike></b>")
            await query.message.edit_reply_markup(reply_markup)
            await query.answer("sᴇᴛ ᴛᴏ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ !")
            content = extract_request_content(query.message.text)
            try:
                await client.send_message(
                    chat_id=int(from_user),
                    text=f"<b>{user.mention},\n\n<u>{content}</u> ʜᴀs ʙᴇᴇɴ ᴍᴀʀᴋᴇᴅ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ... 💔\n\n#ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ ⚠️</b>",
                    reply_markup=InlineKeyboardMarkup(btn2))
            except UserIsBlocked:
                pass
        else:
            await query.answer("ᴀᴄᴄᴇss ᴅᴇɴɪᴇᴅ !", show_alert=True)
            return
        return

    elif query.data.startswith("unalert"):
        ident, from_user = query.data.split("#")
        if int(query.from_user.id) == int(from_user):
            user = await client.get_users(from_user)
            await query.answer(f"{user.first_name},\n\nʏᴏᴜʀ ʀᴇǫᴜᴇꜱᴛ ɪꜱ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ.", show_alert=True)
        else:
            await query.answer("ᴀᴄᴄᴇss ᴅᴇɴɪᴇᴅ !", show_alert=True)
            return
        return

    elif query.data.startswith("Not_Released"):
        ident, from_user = query.data.split("#")
        btn = [[InlineKeyboardButton("🛑 ɴᴏᴛ ʀᴇʟᴇᴀsᴇᴅ 🛑", callback_data=f"nralert#{from_user}")]]
        btn2 = [[
            InlineKeyboardButton('ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟ', url=link.invite_link),
            InlineKeyboardButton("ᴠɪᴇᴡ ꜱᴛᴀᴛᴜꜱ", url=f"{query.message.link}")
        ]]
        if query.from_user.id in ADMINS:
            user = await client.get_users(from_user)
            reply_markup = InlineKeyboardMarkup(btn)
            content = query.message.text
            await query.message.edit_text(f"<b><strike>{content}</strike></b>")
            await query.message.edit_reply_markup(reply_markup)
            await query.answer("sᴇᴛ ᴛᴏ ɴᴏᴛ ʀᴇʟᴇᴀꜱᴇᴅ !")
            content = extract_request_content(query.message.text)
            try:
                await client.send_message(
                    chat_id=int(from_user),
                    text=f"<b>{user.mention}\n\n<u>{content}</u>, ʜᴀꜱ ɴᴏᴛ ʙᴇᴇɴ ʀᴇʟᴇᴀꜱᴇᴅ ʏᴇᴛ\n\n#ɴᴏᴛ_ʀᴇʟᴇᴀꜱᴇᴅ ⛔</b>",
                    reply_markup=InlineKeyboardMarkup(btn2)
                )
            except UserIsBlocked:
                pass
        else:
            await query.answer("ᴀᴄᴄᴇss ᴅᴇɴɪᴇᴅ !", show_alert=True)
            return
        return

    elif query.data.startswith("nralert"):
        ident, from_user = query.data.split("#")
        if int(query.from_user.id) == int(from_user):
            user = await client.get_users(from_user)
            await query.answer(f"{user.first_name},\n\nᴛʜɪꜱ ɪꜱ ɴᴏᴛ ʀᴇʟᴇᴀꜱᴇᴅ ʏᴇᴛ.", show_alert=True)
        else:
            await query.answer("ᴀᴄᴄᴇss ᴅᴇɴɪᴇᴅ !", show_alert=True)
            return
        return

    elif query.data.startswith("already_available"):
        ident, from_user = query.data.split("#")
        btn = [[
            InlineKeyboardButton("♻️ ᴀʟʀᴇᴀᴅʏ ᴀᴠᴀɪʟᴀʙʟᴇ ♻️", callback_data=f"alalert#{from_user}")
        ]]
        btn2 = [[
            InlineKeyboardButton('ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟ', url=link.invite_link),
            InlineKeyboardButton("ᴠɪᴇᴡ ꜱᴛᴀᴛᴜꜱ", url=f"{query.message.link}")
        ], [
            InlineKeyboardButton("ꜱᴇᴀʀᴄʜ ʜᴇʀᴇ", url=GROUP_LINK)
        ]]
        if query.from_user.id in ADMINS:
            user = await client.get_users(from_user)
            reply_markup = InlineKeyboardMarkup(btn)
            content = query.message.text
            await query.message.edit_text(f"<b><strike>{content}</strike></b>")
            await query.message.edit_reply_markup(reply_markup)
            await query.answer("sᴇᴛ ᴛᴏ ᴀʟʀᴇᴀᴅʏ ᴀᴠᴀɪʟᴀʙʟᴇ !")
            content = extract_request_content(query.message.text)
            try:
                await client.send_message(
                    chat_id=int(from_user),
                    text=f"<b>{user.mention},\n\n<u>{content}</u> ʏᴏᴜʀ ʀᴇǫᴜᴇꜱᴛ ɪꜱ ᴀʟʀᴇᴀᴅʏ ᴀᴠᴀɪʟᴀʙʟᴇ ɪɴ ᴏᴜʀ ʙᴏᴛ'ꜱ ᴅᴀᴛᴀʙᴀꜱᴇ.\nᴋɪɴᴅʟʏ sᴇᴀʀᴄʜ ɪɴ ᴏᴜʀ ɢʀᴏᴜᴘ.\n\n#ᴀᴠᴀɪʟᴀʙʟᴇ 💗</b>",
                    reply_markup=InlineKeyboardMarkup(btn2))
            except UserIsBlocked:
                pass
        else:
            await query.answer("ᴀᴄᴄᴇss ᴅᴇɴɪᴇᴅ !", show_alert=True)
            return
        return

    elif query.data.startswith("alalert"):
        ident, from_user = query.data.split("#")
        if int(query.from_user.id) == int(from_user):
            user = await client.get_users(from_user)
            await query.answer(f"{user.first_name},\n\nʏᴏᴜʀ ʀᴇǫᴜᴇsᴛ ɪs ᴀʟʀᴇᴀᴅʏ ᴀᴠᴀɪʟᴀʙʟᴇ.", show_alert=True)
        else:
            await query.answer("ᴀᴄᴄᴇss ᴅᴇɴɪᴇᴅ !", show_alert=True)
            return
        return

    elif query.data.startswith("offtopic"):
        ident, from_user = query.data.split("#")
        btn = [
            [InlineKeyboardButton("🚫 ᴏꜰꜰ - ᴛᴏᴘɪᴄ 🚫", callback_data=f"offalert#{from_user}")]
        ]
        btn2 = [
            [InlineKeyboardButton('ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟ', url=link.invite_link),
             InlineKeyboardButton("ᴠɪᴇᴡ ꜱᴛᴀᴛᴜꜱ", url=f"{query.message.link}")]
        ]
        if query.from_user.id in ADMINS:
            user = await client.get_users(from_user)
            reply_markup = InlineKeyboardMarkup(btn)
            content = query.message.text
            await query.message.edit_text(f"<b><strike>{content}</strike></b>")
            await query.message.edit_reply_markup(reply_markup)
            await query.answer("sᴇᴛ ᴛᴏ ᴏꜰꜰ-ᴛᴏᴘɪᴄ !")
            content = extract_request_content(query.message.text)
            try:
                await client.send_message(
                    chat_id=int(from_user),
                    text=f"<b>{user.mention},\n\n<u>{content}</u> ᴡᴀs ᴍᴀʀᴋᴇᴅ ᴀs ᴏꜰꜰ-ᴛᴏᴘɪᴄ.\nᴘʟᴇᴀsᴇ ᴍᴀᴋᴇ sᴜʀᴇ ᴛᴏ ʀᴇǫᴜᴇsᴛ ᴄᴏɴᴛᴇɴᴛ ʀᴇʟᴀᴛᴇᴅ ᴛᴏ ᴏᴜʀ ᴄᴀᴛᴇɢᴏʀʏ.\n\n#ᴏꜰꜰ_ᴛᴏᴘɪᴄ 🚫</b>",
                    reply_markup=InlineKeyboardMarkup(btn2))
            except UserIsBlocked:
                pass
        else:
            await query.answer("ᴀᴄᴄᴇss ᴅᴇɴɪᴇᴅ !", show_alert=True)
            return
        return

    elif query.data.startswith("offalert"):
        ident, from_user = query.data.split("#")
        if int(query.from_user.id) == int(from_user):
            user = await client.get_users(from_user)
            await query.answer(f"{user.first_name},\n\nᴛʜɪs ʀᴇǫᴜᴇsᴛ ɪsɴ'ᴛ ʀᴇʟᴀᴛᴇᴅ ᴛᴏ ᴏᴜʀ ᴄᴏɴᴛᴇɴᴛ.", show_alert=True)
        else:
            await query.answer("ᴀᴄᴄᴇss ᴅᴇɴɪᴇᴅ !", show_alert=True)
            return
        return

    elif query.data.startswith("Wrong_Spelling"):
        ident, from_user = query.data.split("#")
        btn = [[
            InlineKeyboardButton("📝 ᴡʀᴏɴɢ sᴘᴇʟʟɪɴɢ 📝", callback_data=f"wsalert#{from_user}")
        ]]
        btn2 = [[
            InlineKeyboardButton('ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟ', url=link.invite_link),
            InlineKeyboardButton("ᴠɪᴇᴡ ꜱᴛᴀᴛᴜꜱ", url=f"{query.message.link}")
        ]]
        if query.from_user.id in ADMINS:
            user = await client.get_users(from_user)
            reply_markup = InlineKeyboardMarkup(btn)
            content = query.message.text
            await query.message.edit_text(f"<b><strike>{content}</strike></b>")
            await query.message.edit_reply_markup(reply_markup)
            await query.answer("sᴇᴛ ᴛᴏ ᴄᴏʀʀᴇᴄᴛ sᴘᴇʟʟɪɴɢ !")
            content = extract_request_content(query.message.text)
            try:
                await client.send_message(
                    chat_id=int(from_user),
                    text=f"<b>{user.mention},\n\nᴡᴇ ᴅᴇᴄʟɪɴᴇᴅ ʏᴏᴜʀ ʀᴇǫᴜᴇsᴛ ꜰᴏʀ <u>{content}</u>, ʙᴇᴄᴀᴜsᴇ ʏᴏᴜʀ sᴘᴇʟʟɪɴɢ ᴡᴀs ᴡʀᴏɴɢ.\n\n#ᴡʀᴏɴɢ_ꜱᴘᴇʟʟɪɴɢ 😑</b>",
                    reply_markup=InlineKeyboardMarkup(btn2))
            except UserIsBlocked:
                pass
        else:
            await query.answer("ᴀᴄᴄᴇss ᴅᴇɴɪᴇᴅ !", show_alert=True)
            return
        return

    elif query.data.startswith("wsalert"):
        ident, from_user = query.data.split("#")
        if int(query.from_user.id) == int(from_user):
            user = await client.get_users(from_user)
            await query.answer(f"{user.first_name},\n\nʏᴏᴜʀ ʀᴇǫᴜᴇꜱᴛ ᴡᴀꜱ ʀᴇᴊᴇᴄᴛᴇᴅ ᴅᴜᴇ ᴛᴏ ᴡʀᴏɴɢ sᴘᴇʟʟɪɴɢ.", show_alert=True)
        else:
            await query.answer("ᴀᴄᴄᴇss ᴅᴇɴɪᴇᴅ !", show_alert=True)
            return
        return

    elif query.data.startswith("Not_Available_In_Hindi"):
        ident, from_user = query.data.split("#")
        btn = [[
            InlineKeyboardButton("✨ ɴᴏᴛ ᴀᴠᴀɪʟᴀʙʟᴇ ɪɴ ʜɪɴᴅɪ ✨", callback_data=f"hnalert#{from_user}")
        ]]
        btn2 = [[
            InlineKeyboardButton('ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟ', url=link.invite_link),
            InlineKeyboardButton("ᴠɪᴇᴡ ꜱᴛᴀᴛᴜꜱ", url=f"{query.message.link}")
        ]]
        if query.from_user.id in ADMINS:
            user = await client.get_users(from_user)
            reply_markup = InlineKeyboardMarkup(btn)
            content = query.message.text
            await query.message.edit_text(f"<b><strike>{content}</strike></b>")
            await query.message.edit_reply_markup(reply_markup)
            await query.answer("sᴇᴛ ᴛᴏ ɴᴏᴛ ᴀᴠᴀɪʟᴀʙʟᴇ ɪɴ ʜɪɴᴅɪ !")
            content = extract_request_content(query.message.text)
            try:
                await client.send_message(
                    chat_id=int(from_user),
                    text=f"<b>{user.mention}\n\nʏᴏᴜʀ ʀᴇǫᴜᴇsᴛ <u>{content}</u> ɪs ɴᴏᴛ ᴀᴠᴀɪʟᴀʙʟᴇ ɪɴ ʜɪɴᴅɪ. sᴏ ᴏᴜʀ ᴍᴏᴅᴇʀᴀᴛᴏʀs ᴄᴀɴ'ᴛ ᴜᴘʟᴏᴀᴅ ɪᴛ\n\n#ʜɪɴᴅɪ_ɴᴏᴛ_ᴀᴠᴀɪʟᴀʙʟᴇ ❌</b>",
                    reply_markup=InlineKeyboardMarkup(btn2))
            except UserIsBlocked:
                pass
        else:
            await query.answer("ᴀᴄᴄᴇss ᴅᴇɴɪᴇᴅ !", show_alert=True)
            return
        return

    elif query.data.startswith("hnalert"):
        ident, from_user = query.data.split("#")
        if int(query.from_user.id) == int(from_user):
            user = await client.get_users(from_user)
            await query.answer(f"{user.first_name},\n\nᴛʜɪꜱ ɪꜱ ɴᴏᴛ ᴀᴠᴀɪʟᴀʙʟᴇ ɪɴ ʜɪɴᴅɪ.", show_alert=True)
        else:
            await query.answer("ᴀᴄᴄᴇss ᴅᴇɴɪᴇᴅ !", show_alert=True)
            return
        return

    elif TechifyBots.startswith("generate_stream_link"):
        _, file_id = TechifyBots.split(":")
        try:
            user_id = query.from_user.id
            username = query.from_user.mention
            log_msg = await client.send_cached_media(chat_id=BIN_CHANNEL, file_id=file_id)
            fileName = get_name(log_msg)
            stream = f"{URL}watch/{str(log_msg.id)}/{quote_plus(get_name(log_msg))}?hash={get_hash(log_msg)}"
            download = f"{URL}{str(log_msg.id)}/{quote_plus(get_name(log_msg))}?hash={get_hash(log_msg)}"
            xo = await query.message.reply_text(f'❤‍🔥')
            await asyncio.sleep(1)
            await xo.delete()
            rd = await log_msg.reply_text(
                text=f"‣ ɪᴅ : `{user_id}`\n‣ ʙʏ : {username}\n\n‣ ꜰɪʟᴇ ɴᴀᴍᴇ : {fileName}",
                quote=True,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🖥 sᴛʀᴇᴀᴍ", url=stream),
                                                    InlineKeyboardButton('📥 ᴅᴏᴡɴʟᴏᴀᴅ', url=download)]])
            )
            tb = await query.edit_message_reply_markup(
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("🖥 sᴛʀᴇᴀᴍ ", url=stream),
                        InlineKeyboardButton('📥 ᴅᴏᴡɴʟᴏᴀᴅ', url=download)
                    ],
                    [
                        InlineKeyboardButton('📌 ᴊᴏɪɴ ᴜᴘᴅᴀᴛᴇꜱ ᴄʜᴀɴɴᴇʟ 📌', url=CHANNEL_LINK)
                    ]
                ])
            )
            await asyncio.sleep(DELETE_TIME)
            await tb.delete()
            await log_msg.delete()
            await rd.delete()
            return
        except Exception as e:
            print(e)
            await query.answer(f"⚠️ SOMETHING WENT WRONG STREAM LINK  \n\n{e}", show_alert=True)
            return
            return
        return
        
    elif query.data == "prestream":
        tb = await client.send_photo(
            chat_id=query.message.chat.id,
            photo=random.choice(PICS), 
            caption=script.PRE_STREAM,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💎 ʙᴜʏ ᴘʀᴇᴍɪᴜᴍ 💎", callback_data="premium")]])
        )
        await asyncio.sleep(DELETE_TIME)
        await tb.delete()
        return
        return

    elif query.data == "start":
        buttons = [[
                    InlineKeyboardButton('ᴀʙᴏᴜᴛ 📜', callback_data='about'),
                    InlineKeyboardButton('ᴜᴘɢʀᴀᴅᴇ 🎟', callback_data='premium_info')
                ],[
                     InlineKeyboardButton('🌸 ᴀɴɪᴍᴇ ɢᴜɪᴅᴇ 🌸', user_id=int(OWNER))
                ]]
        reply_markup = InlineKeyboardMarkup(buttons)
        await query.message.edit_media(
            media=InputMediaPhoto(
                media=random.choice(PICS),
                caption=script.START_TXT.format(query.from_user.mention, get_status(), temp.U_NAME, temp.B_NAME),
                parse_mode=enums.ParseMode.HTML
            ),
            reply_markup=reply_markup
        )
        await query.answer(MSG_ALRT)
        return
        return

    elif query.data == "about":
        buttons = [[
            InlineKeyboardButton('⚙️ ᴄᴏɴᴛʀᴏʟ ᴘᴀɴᴇʟ ⚙️', callback_data='controlpanel')
        ],[
            InlineKeyboardButton('ᴅᴍᴄᴀ 📝', callback_data='dmca'),
            InlineKeyboardButton ('ᴅᴏɴᴀᴛᴇ 💰', callback_data='donate')
        ],[
            InlineKeyboardButton('⋞ ʙᴀᴄᴋ ᴛᴏ ʜᴏᴍᴇ', callback_data='start')
        ]]
        reply_markup = InlineKeyboardMarkup(buttons)
        await query.message.edit_media(
            media=InputMediaPhoto(
                media=random.choice(PICS),
                caption=script.ABOUT_TXT.format(temp.U_NAME, temp.B_NAME),
                parse_mode=enums.ParseMode.HTML
            ),
            reply_markup=reply_markup
        )
        return
        return

    elif query.data == "controlpanel":
        buttons = [[
            InlineKeyboardButton('👤  ᴜꜱᴇʀꜱ ᴄᴏᴍᴍᴀɴᴅꜱ  👤', callback_data='user_cmds')
        ],[
            InlineKeyboardButton('ᴀᴅᴍɪɴ 🛠', callback_data='admin_cmds'),
            InlineKeyboardButton ('ɢʀᴏᴜᴘ ꜱᴇᴛᴜᴘ 🔮', callback_data='group_cmds')
        ],[
            InlineKeyboardButton('⋞ ʙᴀᴄᴋ', callback_data='about')
        ]]
        reply_markup = InlineKeyboardMarkup(buttons)
        await query.message.edit_media(
            media=InputMediaPhoto(
                media=random.choice(PICS),
                caption=script.CONTROL_PANEL,
                parse_mode=enums.ParseMode.HTML
            ),
            reply_markup=reply_markup
        )
        return
        return

    elif query.data == "user_cmds":
        await query.message.edit_media(
            media=InputMediaPhoto(
                media=random.choice(PICS),
                caption=script.USER_CMDS.format(query.from_user.mention),
                parse_mode=enums.ParseMode.HTML
            ),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('⋞ ʙᴀᴄᴋ', callback_data='controlpanel')]])
        )
        return
        return

    elif query.data == "admin_cmds":
        if query.from_user.id not in ADMINS:
            return await query.answer('ᴛʜɪꜱ ɪꜱ ɴᴏᴛ ꜰᴏʀ ʏᴏᴜ ʙʀᴏ !', show_alert=True)
        buttons = [[InlineKeyboardButton('🚫 ᴄʟᴏsᴇ 🚫', callback_data='close_data')]]
        reply_markup = InlineKeyboardMarkup(buttons)
        msg = await query.message.reply_text(
            text=script.ADMIN_CMDS.format(query.from_user.mention), 
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML
        )
        await asyncio.sleep(DELETE_TIME)
        await msg.delete()
        return
        return

    elif query.data == "group_cmds":
        buttons = [[
            InlineKeyboardButton('🔰 ᴀᴅᴅ ᴍᴇ ᴛᴏ ʏᴏᴜʀ ɢʀᴏᴜᴘ 🔰', url=f'http://telegram.me/{temp.U_NAME}?startgroup=true')
        ],[
            InlineKeyboardButton('⋞ ʙᴀᴄᴋ', callback_data='controlpanel')
        ]]
        reply_markup = InlineKeyboardMarkup(buttons)
        await query.message.edit_media(
            media=InputMediaPhoto(
                media=random.choice(PICS),
                caption=script.GROUP_CMDS.format(query.from_user.mention),
                parse_mode=enums.ParseMode.HTML
            ),
            reply_markup=reply_markup
        )
        return
        return

    elif query.data == "dmca":
        await query.message.edit_media(
            media=InputMediaPhoto(
                media=random.choice(PICS),
                caption=script.DMCA_TXT,
                parse_mode=enums.ParseMode.HTML
            ),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⋞ ʙᴀᴄᴋ", callback_data="about")]])
        )
        return
        return

    elif query.data == "donate":
        buttons = [[
                InlineKeyboardButton('💳 ᴅᴏɴᴀᴛᴇ ɴᴏᴡ 💳', url='https://TechifyBots.github.io/PayWeb')
            ],[
                InlineKeyboardButton('⋞ ʙᴀᴄᴋ', callback_data='about')
            ]]
        reply_markup = InlineKeyboardMarkup(buttons)
        await query.message.edit_media(
            media=InputMediaPhoto(
                media=random.choice(PICS),
                caption=script.DONATE_TXT.format(query.from_user.mention),
                parse_mode=enums.ParseMode.HTML
            ),
            reply_markup=reply_markup
        )
        return
        return

    elif query.data == "premium_info":
        btn = [[
            InlineKeyboardButton('💎 ʙᴜʏ ᴘʀᴇᴍɪᴜᴍ 💎', callback_data='buy_info')
        ],[
            InlineKeyboardButton('ʀᴇꜰᴇʀ ꜰʀɪᴇɴᴅꜱ 🎁', callback_data='referral'),
            InlineKeyboardButton('ꜰʀᴇᴇ ᴛʀɪᴀʟ ✨', callback_data='free_trial')
        ],[            
            InlineKeyboardButton('⋞ ʙᴀᴄᴋ ᴛᴏ ʜᴏᴍᴇ', callback_data='start')
        ]]
        reply_markup = InlineKeyboardMarkup(btn)                        
        await query.message.edit_media(
            media=InputMediaPhoto(
                media=random.choice(PICS),
                caption=script.PREMIUM_INFO,
                parse_mode=enums.ParseMode.HTML
            ),
            reply_markup=reply_markup
        )
        return
        return

    elif query.data == "buy_info":
        btn = [[
            InlineKeyboardButton('ꜱᴛᴀʀ 🌟', callback_data='star_info'),
            InlineKeyboardButton('ᴜᴘɪ 💳', callback_data='upi_info')
        ],[
            InlineKeyboardButton('⋞ ʙᴀᴄᴋ', callback_data='premium_info')
        ]]
        reply_markup = InlineKeyboardMarkup(btn)
        await query.message.edit_media(
            media=InputMediaPhoto(
                media=random.choice(PICS),
                caption=script.PREMIUM_TEXT,
                parse_mode=enums.ParseMode.HTML
            ),
            reply_markup=reply_markup
        )
        return
        return

    elif query.data == "upi_info":
        btn = [[
            InlineKeyboardButton('📲 ꜱᴇɴᴅ  ᴘᴀʏᴍᴇɴᴛ ꜱᴄʀᴇᴇɴꜱʜᴏᴛ 📲', user_id=int(OWNER))
        ],[
            InlineKeyboardButton('⋞ ʙᴀᴄᴋ', callback_data='buy_info')
        ]]
        reply_markup = InlineKeyboardMarkup(btn)
        await query.message.edit_media(
            media=InputMediaPhoto(
                media=random.choice(PICS),
                caption=script.PREMIUM_UPI_TEXT,
                parse_mode=enums.ParseMode.HTML
            ),
            reply_markup=reply_markup
        )
        return
        return

    elif query.data == "star_info":
        btn = [
            InlineKeyboardButton(f"{stars} ⭐", callback_data=f"buy_{stars}")
            for stars, days in STAR_PREMIUM_PLANS.items()
            ]
        buttons = [btn[i:i + 2] for i in range(0, len(btn), 2)]
        buttons.append([InlineKeyboardButton("⋞ ʙᴀᴄᴋ", callback_data="buy_info")])
        reply_markup = InlineKeyboardMarkup(buttons)
        await query.message.edit_media(
            media=InputMediaPhoto(
                media=random.choice(PICS),
                caption=script.PREMIUM_STAR_TEXT,
                parse_mode=enums.ParseMode.HTML
            ),
            reply_markup=reply_markup
        )
        return
        return

    elif query.data == "ref_point":
        await query.answer(f'ʀᴇꜰᴇʀʀᴀʟ ᴘᴏɪɴᴛꜱ: {referdb.get_refer_points(query.from_user.id)}', show_alert=True)
        return
        return

    elif query.data == "free_trial":
        try:
            user_id = query.from_user.id
            has_free_trial = await db.check_trial_status(user_id)
            if has_free_trial:
                await query.answer("🚸 ʏᴏᴜ'ᴠᴇ ᴀʟʀᴇᴀᴅʏ ᴄʟᴀɪᴍᴇᴅ ʏᴏᴜʀ ꜰʀᴇᴇ ᴛʀɪᴀʟ ᴏɴᴄᴇ !\n\n📌 ᴄʜᴇᴄᴋᴏᴜᴛ ᴏᴜʀ ᴘʟᴀɴꜱ ʙʏ : /plan", show_alert=True)
                return
            else:            
                await db.give_free_trial(user_id)
                await query.answer("ᴛʀɪᴀʟ ᴀᴄᴛɪᴠᴀᴛᴇᴅ ✅", show_alert=True)
                msg = await client.send_photo(
                    chat_id=query.message.chat.id,
                    photo=random.choice(PICS), 
                    caption=script.FREE_TRIAL,
                    parse_mode=enums.ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💎 ʙᴜʏ ᴘʀᴇᴍɪᴜᴍ 💎", callback_data="premium")]])
                )
                await client.send_message(LOG_CHANNEL, text=f"#FREE_TRAIL\n\n👤 ᴜꜱᴇʀ ɴᴀᴍᴇ - {query.from_user.mention}\n⚡ ᴜꜱᴇʀ ɪᴅ - {user_id}", disable_web_page_preview=True)
                await asyncio.sleep(DELETE_TIME)
                return await msg.delete()
        except Exception as e:
            logging.exception("Error in free_trial callback")
            return
        return

    elif query.data == "premium":
        btn = [[
            InlineKeyboardButton('💎 ʙᴜʏ ᴘʀᴇᴍɪᴜᴍ 💎', callback_data='buy_info')
        ],[
            InlineKeyboardButton('ʀᴇꜰᴇʀ ꜰʀɪᴇɴᴅꜱ 🎁', callback_data='referral'),
            InlineKeyboardButton('ꜰʀᴇᴇ ᴛʀɪᴀʟ ✨', callback_data='free_trial')
        ],[            
            InlineKeyboardButton('🚫 ᴄʟᴏꜱᴇ 🚫', callback_data='close_data')
        ]]
        reply_markup = InlineKeyboardMarkup(btn)                        
        await query.message.edit_media(
            media=InputMediaPhoto(
                media=random.choice(PICS),
                caption=script.PREMIUM_INFO,
                parse_mode=enums.ParseMode.HTML
            ),
            reply_markup=reply_markup
        )
        return
        return

    elif query.data.startswith("grp_pm"):
        _, grp_id = query.data.split("#")
        user_id = query.from_user.id if query.from_user else None
        if not await is_check_admin(client, int(grp_id), user_id):
            return await query.answer(script.ADMIN_ALRT_TXT, show_alert=True)
        btn = await group_setting_buttons(int(grp_id))
        tb = await client.get_chat(int(grp_id))
        await query.message.edit(text=f"ᴄʜᴀɴɢᴇ ʏᴏᴜʀ ɢʀᴏᴜᴘ ꜱᴇᴛᴛɪɴɢꜱ ✅\nɢʀᴏᴜᴘ ɴᴀᴍᴇ - '{tb.title}'</b>⚙", reply_markup=InlineKeyboardMarkup(btn))
        return
        return

    elif query.data.startswith("removegrp"):
        user_id = query.from_user.id
        data = query.data
        grp_id = int(data.split("#")[1])
        if not await is_check_admin(client, grp_id, query.from_user.id):
            return await query.answer(script.ADMIN_ALRT_TXT, show_alert=True)
        await db.remove_group_connection(grp_id, user_id)
        await query.answer("ɢʀᴏᴜᴘ ʀᴇᴍᴏᴠᴇᴅ ꜰʀᴏᴍ ʏᴏᴜʀ ᴄᴏɴɴᴇᴄᴛɪᴏɴs.", show_alert=True)
        connected_groups = await db.get_connected_grps(user_id)
        if not connected_groups:
            await query.edit_message_text("ɴᴏ ᴄᴏɴɴᴇᴄᴛᴇᴅ ɢʀᴏᴜᴘ ꜰᴏᴜɴᴅ.")
            return
        group_list = []
        for group in connected_groups:
            try:
                Chat = await client.get_chat(group)
                group_list.append([
                    InlineKeyboardButton(
                        text=Chat.title, callback_data=f"grp_pm#{Chat.id}")
                ])
            except Exception as e:
                print(f"Error In PM Settings Button - {e}")
                pass
        await query.edit_message_text("⚠️ ꜱᴇʟᴇᴄᴛ ᴛʜᴇ ɢʀᴏᴜᴘ ᴡʜᴏꜱᴇ ꜱᴇᴛᴛɪɴɢꜱ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴄʜᴀɴɢᴇ.\n\nɪꜰ ʏᴏᴜʀ ɢʀᴏᴜᴘ ɪꜱ ɴᴏᴛ ꜱʜᴏᴡɪɴɢ ʜᴇʀᴇ,\nᴜꜱᴇ /reload ɪɴ ᴛʜᴀᴛ ɢʀᴏᴜᴘ ᴀɴᴅ ɪᴛ ᴡɪʟʟ ᴀᴘᴘᴇᴀʀ ʜᴇʀᴇ.", reply_markup=InlineKeyboardMarkup(group_list))
        return
        return

    elif query.data.startswith("setgs"):
        ident, set_type, status, grp_id = query.data.split("#")
        userid = query.from_user.id if query.from_user else None
        if not await is_check_admin(client, int(grp_id), userid):
            await query.answer(script.ADMIN_ALRT_TXT, show_alert=True)
            return
        if status == "True":
            await save_group_settings(int(grp_id), set_type, False)
            await query.answer("ᴏꜰꜰ ✗")
        else:
            await save_group_settings(int(grp_id), set_type, True)
            await query.answer("ᴏɴ ✓")
        settings = await get_settings(int(grp_id))
        if settings is not None:
            buttons = await group_setting_buttons(int(grp_id))
            reply_markup = InlineKeyboardMarkup(buttons)
            await query.message.edit_reply_markup(reply_markup)
    await query.answer(MSG_ALRT)

async def auto_filter(client, msg, spoll=False):
    curr_time = datetime.now(pytz.timezone('Asia/Kolkata')).time()

    async def _schedule_delete(sent_obj, orig_msg, delay):
        try:
            await asyncio.sleep(delay)
            try:
                await sent_obj.delete()
            except Exception:
                pass
            try:
                await orig_msg.delete()
            except Exception:
                pass
        except Exception:
            pass
    m = None
    try:
        if not spoll:
            message = msg
            if message.text.startswith("/"):
                return
            if re.findall(r"((^\/|^,|^!|^\.|^[\U0001F600-\U000E007F]).*)", message.text):
                return
            if len(message.text) < 100:
                message_text = message.text or ""
                search = message_text.lower()
                m = await message.reply_text(f"<b><i> 𝖲𝖾𝖺𝗋𝖼𝗁𝗂𝗇𝗀 𝖿𝗈𝗋 '{search}' 🔎</i></b>")
                find = search.split(" ")
                search = ""
                removes = ["in", "upload", "series", "full", "horror", "thriller", "mystery", "print", "file"]
                for x in find:
                    if x in removes:
                        continue
                    else:
                        search = search + x + " "
                search = re.sub(r"\b(pl(i|e)*?(s|z+|ease|se|ese|(e+)s(e)?)|((send|snd|giv(e)?|gib)(\sme)?)|movie(s)?|new|latest|bro|bruh|broh|helo|that|find|dubbed|link|venum|iruka|pannunga|pannungga|anuppunga|anupunga|anuppungga|anupungga|film|undo|kitti|kitty|tharu|kittumo|kittum|movie|any(one)|with\ssubtitle(s)?)", "", search, flags=re.IGNORECASE)
                search = search.replace("-", " ")
                search = re.sub(r"[:']", "", search)
                search = re.sub(r"\s+", " ", search).strip()
                files, offset, total_results = await get_search_results(message.chat.id, search, offset=0, filter=True)
                settings = await get_settings(message.chat.id)
                if not files:
                    if settings.get("spell_check"):
                        ai_sts = await m.edit('🤖 ᴘʟᴇᴀꜱᴇ ᴡᴀɪᴛ, ᴀɪ ɪꜱ ᴄʜᴇᴄᴋɪɴɢ ʏᴏᴜʀ ꜱᴘᴇʟʟɪɴɢ...')
                        is_misspelled = await ai_spell_check(chat_id=message.chat.id, wrong_name=search)
                        if is_misspelled:
                            await ai_sts.edit(f'✅ ᴀɪ sᴜɢɢᴇsᴛᴇᴅ: <code>{is_misspelled}</code>\n🔍 Searching for it...')
                            message.text = is_misspelled
                            await ai_sts.delete()
                            return await auto_filter(client, message)
                        await ai_sts.delete()
                        result = await advantage_spell_chok(client, message)
                        return result
                    else:
                        try:
                            if m:
                                await m.delete()
                        except Exception:
                            pass
                        result = await advantage_spell_chok(client, message)
                        return result
            else:
                return
        else:
            message = msg.message.reply_to_message
            search, files, offset, total_results = spoll
            m = await message.reply_text(f'🔎 sᴇᴀʀᴄʜɪɴɢ {search}', reply_to_message_id=message.id)
            settings = await get_settings(message.chat.id)
            await msg.message.delete()
        key = f"{message.chat.id}-{message.id}"
        FRESH[key] = search
        temp.GETALL[key] = files
        temp.SHORT[message.from_user.id] = message.chat.id
        if settings.get('button'):
            btn = [
                [InlineKeyboardButton(text=f"{get_size(file.file_size)} ≽ clean_filename(file.file_name)", callback_data=f'file#{file.file_id}')]
                for file in files
            ]
            if offset != "":
                btn.insert(0, [
                    InlineKeyboardButton("ǫᴜᴀʟɪᴛʏ", callback_data=f"qualities#{key}"),
                    InlineKeyboardButton("ʟᴀɴɢᴜᴀɢᴇ", callback_data=f"languages#{key}"),
                    InlineKeyboardButton("sᴇᴀsᴏɴ", callback_data=f"seasons#{key}")
                ])
                btn.insert(0, [
                    InlineKeyboardButton("📥 sᴇɴᴅ ᴀʟʟ ꜰɪʟᴇs 📥", callback_data=f"sendfiles#{key}")
                ])
            else:
                btn.insert(0, [
                    InlineKeyboardButton("📥 sᴇɴᴅ ᴀʟʟ ꜰɪʟᴇs 📥", callback_data=f"sendfiles#{key}")
                ])
        else:
            btn = []
            if offset != "":
                btn.insert(0, [
                    InlineKeyboardButton("ǫᴜᴀʟɪᴛʏ", callback_data=f"qualities#{key}"),
                    InlineKeyboardButton("ʟᴀɴɢᴜᴀɢᴇ", callback_data=f"languages#{key}"),
                    InlineKeyboardButton("sᴇᴀsᴏɴ", callback_data=f"seasons#{key}")
                ])
                btn.insert(0, [
                    InlineKeyboardButton("📥 sᴇɴᴅ ᴀʟʟ ꜰɪʟᴇs 📥", callback_data=f"sendfiles#{key}")
                ])
            else:
                btn.insert(0, [
                    InlineKeyboardButton("📥 sᴇɴᴅ ᴀʟʟ ꜰɪʟᴇs 📥", callback_data=f"sendfiles#{key}")
                ])

        if offset != "":
            req = message.from_user.id if message.from_user else 0
            if FAST_MODE:
                btn.append([InlineKeyboardButton(text="1", callback_data="pages"), InlineKeyboardButton(text="ɴᴇxᴛ ⋟", callback_data=f"next_{req}_{key}_{offset}")])
            else:
                try:
                    if settings['max_btn']:
                        btn.append([InlineKeyboardButton(text=f"1/{math.ceil(int(total_results)/10)}", callback_data="pages"), InlineKeyboardButton(text="ɴᴇxᴛ ⋟", callback_data=f"next_{req}_{key}_{offset}")])
                    else:
                        btn.append([InlineKeyboardButton(text=f"1/{math.ceil(int(total_results)/int(MAX_BTNS))}", callback_data="pages"), InlineKeyboardButton(text="ɴᴇxᴛ ⋟", callback_data=f"next_{req}_{key}_{offset}")])
                except KeyError:
                    await save_group_settings(message.chat.id, 'max_btn', True)
                    btn.append([InlineKeyboardButton(text=f"1/{math.ceil(int(total_results)/10)}", callback_data="pages"), InlineKeyboardButton(text="ɴᴇxᴛ ⋟", callback_data=f"next_{req}_{key}_{offset}")])
        else:
            btn.append([InlineKeyboardButton(text="🚸 ɴᴏ ᴍᴏʀᴇ ᴘᴀɢᴇs 🚸", callback_data="pages")])

        if settings.get('imdb'):
            imdb = await get_posterx(search, file=(files[0]).file_name) if TMDB_POSTER else await get_poster(search, file=(files[0]).file_name)
        else:
            imdb = None

        cur_time = datetime.now(pytz.timezone('Asia/Kolkata')).time()
        time_difference = timedelta(hours=cur_time.hour, minutes=cur_time.minute, seconds=(cur_time.second+(cur_time.microsecond/1000000))) - \
            timedelta(hours=curr_time.hour, minutes=curr_time.minute,
                      seconds=(curr_time.second+(curr_time.microsecond/1000000)))
        remaining_seconds = "{:.2f}".format(time_difference.total_seconds())

        TEMPLATE = script.IMDB_TEMPLATE_TXT
        settings = await get_settings(message.chat.id)
        if settings.get('template'):
            TEMPLATE = settings['template']

        if imdb:
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
                cast=imdb['cast'],
                runtime=imdb['runtime'],
                countries=imdb['countries'],
                certificates=imdb['certificates'],
                languages=imdb['languages'],
                director=imdb['director'],
                writer=imdb['writer'],
                producer=imdb['producer'],
                composer=imdb['composer'],
                cinematographer=imdb['cinematographer'],
                music_team=imdb['music_team'],
                distributors=imdb['distributors'],
                release_date=imdb['release_date'],
                year=imdb['year'],
                genres=imdb['genres'],
                poster=imdb['poster'],
                plot=imdb['plot'] if settings.get('button') else "N/A",
                rating=imdb['rating'],
                url=imdb['url'],
                **locals()
            )
            temp.IMDB_CAP[message.from_user.id] = cap
            if not settings.get('button'):
                cap += "\n\n<b>♻️ <u>ʀᴇꜱᴜʟᴛꜱ ꜰᴏʀ ʏᴏᴜʀ sᴇᴀʀᴄʜ</u></b>"
                for idx, file in enumerate(files, start=1):
                    cap += f"<b>\n{idx}. <a href='https://telegram.me/{temp.U_NAME}?start=file_{message.chat.id}_{file.file_id}'>[{get_size(file.file_size)}] {clean_filename(file.file_name)}\n</a></b>"
        else:
            temp.IMDB_CAP[message.from_user.id] = None
            if FAST_MODE:
                if settings.get('button'):
                    cap = f"<b>🙋‍♂ {message.from_user.mention}\n⏰ ʀᴇsᴜʟᴛ ɪɴ : <code>{remaining_seconds}</code> ꜱᴇᴄᴏɴᴅs\n\n♻️ <u>ʀᴇꜱᴜʟᴛꜱ ꜰᴏʀ ʏᴏᴜʀ sᴇᴀʀᴄʜ</u>\n\n</b>"
                else:
                    cap = f"<b>🙋‍♂ {message.from_user.mention}\n⏰ ʀᴇsᴜʟᴛ ɪɴ : <code>{remaining_seconds}</code> ꜱᴇᴄᴏɴᴅs\n\n♻️ <u>ʀᴇꜱᴜʟᴛꜱ ꜰᴏʀ ʏᴏᴜʀ sᴇᴀʀᴄʜ</u>\n\n</b>"
                    for idx, file in enumerate(files, start=1):
                        cap += f"<b>\n{idx}. <a href='https://telegram.me/{temp.U_NAME}?start=file_{message.chat.id}_{file.file_id}'>[{get_size(file.file_size)}] {clean_filename(file.file_name)}\n</a></b>"
            else:
                if settings.get('button'):
                    cap = f"<b>🙋‍♂ {message.from_user.mention}\n📝 ᴛᴏᴛᴀʟ ꜰɪʟᴇꜱ : <code>{total_results}</code>\n\n♻️ <u>ʀᴇꜱᴜʟᴛꜱ ꜰᴏʀ ʏᴏᴜʀ sᴇᴀʀᴄʜ</u>\n\n</b>"
                else:
                    cap = f"<b>🙋‍♂ {message.from_user.mention}\n📝 ᴛᴏᴛᴀʟ ꜰɪʟᴇꜱ : <code>{total_results}</code>\n\n♻️ <u>ʀᴇꜱᴜʟᴛꜱ ꜰᴏʀ ʏᴏᴜʀ sᴇᴀʀᴄʜ</u>\n\n</b>"

                    for idx, file in enumerate(files, start=1):
                        cap += f"<b>\n{idx}. <a href='https://telegram.me/{temp.U_NAME}?start=file_{message.chat.id}_{file.file_id}'>[{get_size(file.file_size)}] {clean_filename(file.file_name)}\n</a></b>"
        sent = None
        try:
            if imdb and imdb.get('poster'):
                try:
                    if TMDB_POSTER:
                        photo = imdb.get('backdrop') if imdb.get('backdrop') and LANDSCAPE_POSTER else imdb.get('poster')
                    else:
                        photo = imdb.get('poster')
                    sent = await message.reply_photo(photo=photo, caption=cap, reply_markup=InlineKeyboardMarkup(btn), parse_mode=enums.ParseMode.HTML)
                    if m:
                        await m.delete()
                except (MediaEmpty, PhotoInvalidDimensions, WebpageMediaEmpty):
                    pic = imdb.get('poster')
                    poster = pic.replace('.jpg', "._V1_UX360.jpg")
                    sent = await message.reply_photo(photo=poster, caption=cap, reply_markup=InlineKeyboardMarkup(btn), parse_mode=enums.ParseMode.HTML)
                    if m:
                        await m.delete()
                except Exception as e:
                    logger.exception(e)
                    sent = await message.reply_text(text=cap, reply_markup=InlineKeyboardMarkup(btn), disable_web_page_preview=True, parse_mode=enums.ParseMode.HTML)
            else:
                sent = await message.reply_text(text=cap, reply_markup=InlineKeyboardMarkup(btn), disable_web_page_preview=True, parse_mode=enums.ParseMode.HTML)
                if m:
                    await m.delete()
        except Exception as e:
            logger.exception("Failed to send result: %s", e)
            return
        try:
            if settings.get('auto_delete'):
                asyncio.create_task(_schedule_delete(sent, message, DELETE_TIME))
        except KeyError:
            try:
                await save_group_settings(message.chat.id, 'auto_delete', True)
            except Exception:
                pass
            asyncio.create_task(_schedule_delete(sent, message, DELETE_TIME))
        return
    except Exception as e:
        logger.exception(e)
        return

async def ai_spell_check(chat_id, wrong_name):
    async def search_movie(wrong_name):
        search_results = imdb.search_movie(wrong_name)
        if not search_results or not hasattr(search_results, "titles"):
            return []
        movie_list = [movie.title for movie in search_results.titles]
        return movie_list
    movie_list = await search_movie(wrong_name)
    if not movie_list:
        return
    for _ in range(5):
        closest_match = process.extractOne(wrong_name, movie_list)
        if not closest_match or closest_match[1] <= 80:
            return
        movie = closest_match[0]
        files, _, _ = await get_search_results(chat_id=chat_id, query=movie)
        if files:
            return movie
        movie_list.remove(movie)

async def advantage_spell_chok(client, message):
    mv_id = message.id
    search = message.text
    chat_id = message.chat.id
    settings = await get_settings(chat_id)
    query = re.sub(
        r"\b(pl(i|e)*?(s|z+|ease|se|ese|(e+)s(e)?)|((send|snd|giv(e)?|gib)(\sme)?)|movie(s)?|new|latest|br((o|u)h?)*|^h(e|a)?(l)*(o)*|mal(ayalam)?|t(h)?amil|file|that|find|und(o)*|kit(t(i|y)?)?o(w)?|thar(u)?(o)*w?|kittum(o)*|aya(k)*(um(o)*)?|full\smovie|any(one)|with\ssubtitle(s)?)",
        "", message.text, flags=re.IGNORECASE)
    query = query.strip() + " movie"
    try:
        movies = await get_poster(search, bulk=True)
    except Exception as e:
        logger.exception("get_poster failed for query=%s: %s", query, e)
        try:
            k = await message.reply(script.I_CUDNT.format(message.from_user.mention))
            await asyncio.sleep(60)
            try:
                await k.delete()
            except Exception:
                pass
        except Exception:
            pass
        try:
            await message.delete()
        except Exception:
            pass
        return
    if not movies:
        google = quote_plus(search)
        button = [[InlineKeyboardButton("🔍 ᴄʜᴇᴄᴋ sᴘᴇʟʟɪɴɢ ᴏɴ ɢᴏᴏɢʟᴇ 🔍", url=f"https://www.google.com/search?q={google}")]]
        k = await message.reply_text(text=script.I_CUDNT.format(search), reply_markup=InlineKeyboardMarkup(button))
        await asyncio.sleep(60)
        await k.delete()
        try:
            await message.delete()
        except:
            pass
        return
    user = message.from_user.id if message.from_user else 0
    buttons = [[InlineKeyboardButton(text=movie.title, callback_data=f"spol#{movie.imdb_id}#{user}")] for movie in movies]
    buttons.append([InlineKeyboardButton(text="🚫 ᴄʟᴏsᴇ 🚫", callback_data='close_data')])
    d = await message.reply_text(text=script.CUDNT_FND.format(message.from_user.mention), reply_markup=InlineKeyboardMarkup(buttons), reply_to_message_id=message.id)
    await asyncio.sleep(60)
    await d.delete()
    try:
        await message.delete()
    except:
        pass
