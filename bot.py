import sys
import time
import traceback
from datetime import datetime
import asyncio
from asyncio import sleep
from pyrogram import idle, __version__
from pyrogram.raw.all import layer
from pyrogram.errors import FloodWait
from pytz import timezone
from pathlib import Path
import importlib.util
from aiohttp import web
from PIL import Image
Image.MAX_IMAGE_PIXELS = 500_000_000
from database.ia_filterdb import Media, Media2
from pymongo.errors import OperationFailure
from database.users_chats_db import db
from info import *
from utils import temp
from Script import script
import plugins.cover
from plugins.route import routes
from web import techifybots
from web.clients import initialize_clients
import logging
import logging.config

logging.basicConfig(level=logging.INFO)
logging.config.fileConfig('logging.conf')
logging.getLogger().setLevel(logging.INFO)
logging.getLogger("pyrogram").setLevel(logging.ERROR)
logging.getLogger("imdbpy").setLevel(logging.ERROR)
logging.getLogger("aiohttp").setLevel(logging.ERROR)
logging.getLogger("aiohttp.web").setLevel(logging.ERROR)
logging.getLogger("pymongo").setLevel(logging.WARNING)


async def ensure_media_indexes(media_model):
    """Ensure umongo indexes without crashing on existing text-index variants.

    MongoDB permits only one text index per collection. Existing deployments may
    already have a compatible text index with caption support, so tolerate the
    resulting IndexOptionsConflict instead of aborting startup.
    """
    try:
        await media_model.ensure_indexes()
    except OperationFailure as exc:
        if exc.code != 85:
            raise

        indexes = await media_model.collection.index_information()
        has_text_index = any(
            any(index_type == "text" for _, index_type in index.get("key", []))
            for index in indexes.values()
        )
        if not has_text_index:
            raise

        logging.warning(
            "Skipping %s text index creation because an existing text index is present: %s",
            media_model.__name__,
            ", ".join(indexes.keys()),
        )
        
botStartTime = time.time()

async def web_server():
    web_app = web.Application(client_max_size=30000000)
    web_app.add_routes(routes)
    return web_app

async def check_expired_premium(client):
    while 1:
        data = await db.get_expired(datetime.now())
        for user in data:
            user_id = user["id"]
            await db.remove_premium_access(user_id)
            try:
                user = await client.get_users(user_id)
                await client.send_message(
                    chat_id=user_id,
                    text=f"<b>{user.mention},\n\nʏᴏᴜʀ ᴘʀᴇᴍɪᴜᴍ ᴀᴄᴄᴇss ʜᴀs ᴇxᴘɪʀᴇᴅ.\nᴄʜᴇᴄᴋ /plan ᴛᴏ ᴠɪᴇᴡ ᴏᴜʀ ᴄᴜʀʀᴇɴᴛ ᴘʟᴀɴs.</b>"
                )
                await client.send_message(PREMIUM_LOGS, text=f"<b>#Premium_Expire\n\nUser name: {user.mention}\nUser id: <code>{user_id}</code>")
            except Exception as e:
                print(e)
            await sleep(0.5)
        await sleep(1)

async def keep_alive():
    async with aiohttp.ClientSession() as session:
        while True:
            await asyncio.sleep(298)
            try:
                async with session.get(URL) as resp:
                    if resp.status != 200:
                        logging.warning(f"⚠️ Ping Error! Status: {resp.status}")
            except Exception as e:
                logging.error(f"❌ Ping Failed: {e}")

async def ping_server():
    sleep_time = PING_INTERVAL
    while True:
        await asyncio.sleep(sleep_time)
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            ) as session:
                async with session.get(URL) as resp:
                    logging.info("Pinged server with response: {}".format(resp.status))
        except TimeoutError:
            logging.warning("Couldn't connect to the site URL..!")
        except Exception:
            traceback.print_exc()

def techifybots_plugins_handler(app, plugins_dir: str | Path = "plugins", package_name: str = "plugins") -> list[str]:
    plugins_dir = Path(plugins_dir)
    loaded_plugins: list[str] = []
    if not plugins_dir.exists():
        logging.warning("Plugins Directory '%s' Does Not Exist.", plugins_dir)
        return loaded_plugins
    for file in sorted(plugins_dir.rglob("*.py")):
        if file.name == "__init__.py":
            continue
        rel_path = file.relative_to(plugins_dir).with_suffix("")
        import_path = package_name + ".".join([""] + list(rel_path.parts))
        try:
            spec = importlib.util.spec_from_file_location(import_path, file)
            if spec is None or spec.loader is None:
                logging.warning("Skipping %s (No Spec/Loader).", file)
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            sys.modules[import_path] = module
            loaded_plugins.append(import_path)
            short_name = import_path.removeprefix(f"{package_name}.")
            logging.info("🔌 Loaded plugin: %s", short_name)
        except Exception:
            logging.exception("Failed To Import Plugin: %s", import_path)
    disp = getattr(app, "dispatcher", None)
    if disp is None:
        logging.warning("App Has No Dispatcher; Skipping Handler Regroup.")
        return loaded_plugins
    if 0 in disp.groups:
        all_handlers = list(disp.groups[0])
        for i, handler in enumerate(all_handlers):
            disp.remove_handler(handler, group=0)
            disp.add_handler(handler, group=i)
    else:
        logging.info("No Handlers In Group 0; Nothing To Regroup.")
    return loaded_plugins

async def techifybots_start():
    print('\n\nInitalizing ')
    await techifybots.start()
    bot_info = await techifybots.get_me()
    techifybots.username = bot_info.username
    await initialize_clients()
    loaded_plugins = techifybots_plugins_handler(techifybots)
    if loaded_plugins:
        logging.info("✅ Plugins Loaded: %d", len(loaded_plugins))
    else:
        logging.info("⚠️ No Plugins Loaded.")
    if ON_HEROKU:
        asyncio.create_task(ping_server()) 
    b_users, b_chats = await db.get_banned()
    temp.BANNED_USERS = b_users
    temp.BANNED_CHATS = b_chats
    await ensure_media_indexes(Media)
    if MULTIPLE_DB:
        await ensure_media_indexes(Media2)
        print("Multiple Database Mode On. Now Files Will Be Save In Second DB If First DB Is Full")
    else:
        print("Single DB Mode On ! Files Will Be Save In First Database")
    me = await techifybots.get_me()
    temp.ME = me.id
    temp.U_NAME = me.username
    temp.B_NAME = me.first_name
    temp.B_LINK = me.mention
    techifybots.username = '@' + me.username
    techifybots.loop.create_task(check_expired_premium(techifybots))
    logging.info(f"{me.first_name} with Pyrogram v{__version__} (Layer {layer}) started on {me.username}.")
    logging.info(LOG_STR)
    logging.info(script.LOGO)
    now = datetime.now(timezone("Asia/Kolkata"))
    await techifybots.send_message(chat_id=LOG_CHANNEL, text=f"**{temp.B_LINK} is restarted!**\n\n📅 Date : `{now.strftime('%d %B, %Y')}`\n⏰ Time : `{now.strftime('%I:%M:%S %p')}`\n🌐 Timezone : `Asia/Kolkata`")
    for admin_id in ADMINS:
        try:
            await techifybots.send_message(chat_id=int(admin_id), text=f"🤖 {temp.B_NAME} Restarted Successfully ✅")
        except Exception as e:
            logging.warning(f"Couldn't send restart message to admin {admin_id}: {e}")
    app = web.AppRunner(await web_server())
    await app.setup()
    bind_address = "0.0.0.0"
    await web.TCPSite(app, bind_address, PORT).start()
    techifybots.loop.create_task(keep_alive())
    await idle()
    
if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    while True:
        try:
            loop.run_until_complete(techifybots_start())
            break  
        except FloodWait as e:
            print(f"FloodWait! Sleeping for {e.value} seconds.")
            time.sleep(e.value) 
        except KeyboardInterrupt:
            logging.info('Service Stopped Bye 👋')
            break
