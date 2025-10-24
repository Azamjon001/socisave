import os
import asyncio
import logging
import tempfile
import yt_dlp
import re
import random
import time
import requests
from pyrogram import Client, filters, InputMediaPhoto
from pyrogram.errors import BadRequest, BadMsgNotification

API_ID = 29683541
API_HASH = "3a9d6a1205003b0145bc9b6b8d8e1193"
BOT_TOKEN = "6788128988:AAF1lnBqcl1PDDuTw7ONKXrUpNfR1oh4Ggw"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------------- SafeClient -------------------------
class SafeClient(Client):
    async def send(self, *args, **kwargs):
        for attempt in range(3):
            try:
                return await super().send(*args, **kwargs)
            except BadMsgNotification as e:
                if e.error_code == 16:
                    logger.warning(f"[WARN] BadMsgNotification [16], попытка {attempt + 1}/3")
                    self.session.msg_id_offset = int(time.time() * 2**32)
                    await asyncio.sleep(1)
                else:
                    raise
        raise RuntimeError("Ошибка синхронизации msg_id с Telegram")

# ------------------------- инициализация клиента -------------------------
app = SafeClient(
    "fast_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    sleep_threshold=15
)

# ------------------------- вспомогательные функции -------------------------
def extract_first_url(text: str) -> str:
    match = re.search(r"(https?://[^\s]+)", text)
    return match.group(1) if match else ""

def normalize_url(url: str) -> str:
    if "youtu.be/" in url:
        video_id = url.split("/")[-1].split("?")[0]
        return f"https://www.youtube.com/watch?v={video_id}"
    return url

# ------------------------- Instagram функции -------------------------
def get_instagram_info(url: str) -> dict:
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "cookies": "cookies.txt",
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception as e:
        logger.error(f"Ошибка получения данных Instagram: {e}")
        return None

def detect_instagram_content_type(info: dict) -> str:
    if not info:
        return "unknown"

    if info.get("duration"):
        return "video"

    if info.get("_type") == "playlist":
        entries = info.get("entries", [])
        if entries:
            if entries[0].get("duration"):
                return "video_carousel"
            return "photo_carousel"

    if "formats" in info:
        for f in info["formats"]:
            if f.get("vcodec") not in (None, "none"):
                return "video"

    return "photo_single"

def download_instagram_video(info: dict, output_dir: str) -> str:
    ydl_opts = {
        "outtmpl": os.path.join(output_dir, "%(title).50s.%(ext)s"),
        "format": "best[ext=mp4]/best",
        "cookies": "cookies.txt",
        "quiet": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.process_info(info)
        return ydl.prepare_filename(info)

def download_instagram_photo_direct(info: dict, output_dir: str) -> list:
    downloaded_files = []
    urls = []

    if info.get("_type") == "playlist":
        for entry in info.get("entries", []):
            if entry.get("url") and not entry.get("duration"):
                urls.append(entry["url"])
    elif info.get("url"):
        urls.append(info["url"])

    for i, photo_url in enumerate(urls):
        try:
            r = requests.get(photo_url, stream=True, timeout=20)
            if r.status_code == 200:
                ext = ".jpg"
                if ".png" in photo_url:
                    ext = ".png"
                elif ".webp" in photo_url:
                    ext = ".webp"
                filename = os.path.join(output_dir, f"photo_{i+1}{ext}")
                with open(filename, "wb") as f:
                    for chunk in r.iter_content(8192):
                        f.write(chunk)
                downloaded_files.append(filename)
        except Exception as e:
            logger.error(f"Ошибка при скачивании фото {i+1}: {e}")
    return downloaded_files

# ------------------------- YouTube функции -------------------------
def get_youtube_direct_url(url: str) -> str:
    ydl_opts = {"quiet": True, "skip_download": True, "format": "mp4[height<=720]/best[ext=mp4]/best"}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return info.get("url")

def download_youtube_video(url: str, out_path: str) -> str:
    ydl_opts = {
        "outtmpl": os.path.join(out_path, "%(title).50s.%(ext)s"),
        "format": "best[height<=720][ext=mp4]/best[ext=mp4]",
        "noplaylist": True,
        "quiet": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)

# ------------------------- хэндлеры -------------------------
@app.on_message(filters.command("start"))
async def start(_, message):
    await message.reply_text(
        "👋 Привет!\n\n"
        "📥 Отправь ссылку на Instagram — я скачаю фото или видео для тебя.\n"
        "🎥 Или ссылку на YouTube — скачаю видео."
    )

@app.on_message(filters.text & ~filters.command("start"))
async def handle_text(_, message):
    url = extract_first_url(message.text)
    if not url or not any(d in url for d in ["instagram.com", "youtube.com", "youtu.be"]):
        await message.delete()
        return

    status = await message.reply_text("🔍 Анализируем ссылку...")
    try:
        url = normalize_url(url)

        # ---------------- YouTube ----------------
        if "youtube" in url or "youtu.be" in url:
            tmp_dir = tempfile.mkdtemp()
            try:
                direct_url = await asyncio.to_thread(get_youtube_direct_url, url)
                await message.reply_video(direct_url, caption="📥 YouTube видео")
            except:
                file_path = await asyncio.to_thread(download_youtube_video, url, tmp_dir)
                await message.reply_video(file_path, caption="📥 YouTube видео")
                os.remove(file_path)
            os.rmdir(tmp_dir)

        # ---------------- Instagram ----------------

elif "instagram.com" in url:
    await status.edit_text("📡 Получаем данные поста...")
    info = await asyncio.to_thread(get_instagram_info, url)

    if not info:
        await status.edit_text("❌ Не удалось получить информацию о посте.")
        return

    content_type = await asyncio.to_thread(detect_instagram_content_type, info)
    logger.info(f"Тип контента: {content_type}")

    tmp_dir = tempfile.mkdtemp()

    if content_type == "video":
        await status.edit_text("🎥 Скачиваем видео...")
        video_path = await asyncio.to_thread(download_instagram_video, info, tmp_dir)
        await message.reply_video(video_path, caption="📥 Instagram видео")
        os.remove(video_path)

    elif content_type in ["photo_single", "photo_carousel"]:
        await status.edit_text("📸 Скачиваем фото...")
        # ⚡ Никогда не вызываем download_instagram_video для фото
        photo_paths = await asyncio.to_thread(download_instagram_photo_direct, info, tmp_dir)

        if len(photo_paths) == 1:
            await message.reply_photo(photo_paths[0], caption="📸 Instagram фото")
        elif len(photo_paths) > 1:
            media_group = [InputMediaPhoto(p) for p in photo_paths]
            media_group[0].caption = "📸 Instagram карусель"
            await message.reply_media_group(media_group)
        else:
            await status.edit_text("❌ Не удалось скачать фото.")

        for p in photo_paths:
            os.remove(p)

    else:
        await status.edit_text("⚠️ Неизвестный тип контента.")

    os.rmdir(tmp_dir)



        await status.delete()
        await message.delete()

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await status.edit_text(f"❌ Ошибка: {e}")
        await asyncio.sleep(5)
        await status.delete()

# ------------------------- запуск -------------------------
if __name__ == "__main__":
    if not os.path.exists("downloads"):
        os.makedirs("downloads")
    app.run()
