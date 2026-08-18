import os
import logging
import httpx
import yt_dlp
from pyrogram import Client, filters
from info import LOG_CHANNEL

logger = logging.getLogger(__name__)

async def log_download_copy(client, downloaded_file, thumbnail_file, message, link, title, duration):
    if not LOG_CHANNEL:
        return
    try:
        user = message.from_user
        user_id = user.id if user else "N/A"
        mention = user.mention if user else "Unknown User"
        username = f"@{user.username}" if user and user.username else "N/A"

        log_caption = (
            f"🎬 **Video Downloaded via /download**\n\n"
            f"👤 **User:** {mention} (`{user_id}`)\n"
            f"<b>Username:</b> {username}\n"
            f"📌 **Title:** {title}\n"
            f"🔗 **URL:** {link}"
        )

        thumb = thumbnail_file if thumbnail_file and os.path.exists(thumbnail_file) else None

        await client.send_video(
            chat_id=LOG_CHANNEL,
            video=downloaded_file,
            caption=log_caption,
            duration=duration,
            thumb=thumb,
        )
    except Exception as e:
        logger.error(f"Failed to log download copy: {e}")

@Client.on_message(filters.command('download'))
async def download_video(client, message):
    if len(message.command) > 1:
        link = message.command[1]
    else:
        return await message.reply("⚠️ <b>Missing Video Link!</b>\n\n<blockquote><b>Usage:</b> <code>/download https://youtube.com/watch?v=...</code></blockquote>")

    status_msg = await message.reply("⏳ Downloading video, please wait...")

    user_id = message.from_user.id if message.from_user else 0
    downloaded_file = None
    thumbnail_file = None

    try:
        os.makedirs("yt_dlp_downloads", exist_ok=True)

        ydl_opts = {
            'outtmpl': f'yt_dlp_downloads/{user_id}_%(title)s.%(ext)s',
            'format': 'bestvideo+bestaudio/best[vcodec!=none][acodec!=none]/best',
            'quiet': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(link, download=True)
            title = info.get('title', 'Video')
            duration = info.get('duration', 0)
            thumbnail_url = info.get('thumbnail', None)
            downloaded_file = ydl.prepare_filename(info)

        if thumbnail_url:
            thumbnail_file = f"yt_dlp_downloads/{user_id}_thumb.jpg"
            try:
                async with httpx.AsyncClient() as http:
                    response = await http.get(thumbnail_url)
                    if response.status_code == 200:
                        with open(thumbnail_file, 'wb') as f:
                            f.write(response.content)
                    else:
                        thumbnail_file = None
            except Exception as e:
                logger.error(f"Failed to download thumbnail: {e}")
                thumbnail_file = None

        await status_msg.edit("📤 Uploading to Telegram...")

        thumb = thumbnail_file if thumbnail_file and os.path.exists(thumbnail_file) else None

        await client.send_video(
            chat_id=message.chat.id,
            video=downloaded_file,
            caption=f"🎬 **{title}**",
            duration=duration,
            thumb=thumb,
            reply_to_message_id=message.id,
        )
        await log_download_copy(client, downloaded_file, thumb, message, link, title, duration)

        await status_msg.delete()

    except yt_dlp.utils.DownloadError as e:
        await status_msg.edit(f"❌ <b>Download Failed!</b>\n\n<blockquote><code>{str(e)}</code></blockquote>")

    except Exception as e:
        await status_msg.edit(f"❌ <b>An Error Occurred!</b>\n\n<blockquote><code>{str(e)}</code></blockquote>")

    finally:
        if downloaded_file and os.path.exists(downloaded_file):
            try:
                os.remove(downloaded_file)
            except Exception as e:
                logger.error(f"Failed to remove downloaded file: {e}")
        if thumbnail_file and os.path.exists(thumbnail_file):
            try:
                os.remove(thumbnail_file)
            except Exception as e:
                logger.error(f"Failed to remove thumbnail file: {e}")
