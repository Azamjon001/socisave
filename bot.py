import os
import asyncio
import logging
import tempfile
import yt_dlp
import re
import random
import time
import requests
from pyrogram import Client, filters
from pyrogram.errors import BadRequest, BadMsgNotification

API_ID = 26670278
API_HASH = "e3d77390fd9c22d98bb6bddca86fef1a"
BOT_TOKEN = "6788128988:AAEMmCSafiiEqtS5UWQQxfo--W0On7B6Q08"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------------- SafeClient для Railway -------------------------
class SafeClient(Client):
    async def send(self, *args, **kwargs):
        """
        Переопределяем метод отправки, чтобы исправлять msg_id при ошибке [16].
        """
        for attempt in range(3):
            try:
                return await super().send(*args, **kwargs)
            except BadMsgNotification as e:
                if e.error_code == 16:
                    logger.warning(f"[WARN] BadMsgNotification [16], исправляем msg_id, попытка {attempt + 1}/3")
                    self.session.msg_id_offset = int(time.time() * 2**32)
                    await asyncio.sleep(1)
                else:
                    raise
        raise RuntimeError("Не удалось синхронизировать msg_id с Telegram")

# ------------------------- ИЗМЕНЕНО: новое имя сессии -------------------------
app = SafeClient(
    "video_bot_new_session_2024",  # ⬅️ ИЗМЕНИЛ ИМЯ СЕССИИ!
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
        "retries": 1,
        "merge_output_format": "mp4",
        "concurrent_fragment_downloads": 4,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)

# ✅ ИСПРАВЛЕНО: Instagram функции с правильным использованием cookies
def check_cookies_file():
    """Проверяем наличие cookies файла"""
    if not os.path.exists("cookies.txt"):
        logger.error("❌ Файл cookies.txt не найден!")
        return False
    logger.info("✅ Файл cookies.txt найден")
    return True

def get_instagram_url(url: str) -> str:
    """Получаем прямую ссылку на Instagram видео"""
    if not check_cookies_file():
        raise FileNotFoundError("Файл cookies.txt не найден. Instagram недоступен.")
    
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "format": "best[ext=mp4]/best",
        "cookiefile": "cookies.txt",
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get("url")
    except Exception as e:
        logger.error(f"Ошибка получения Instagram URL: {e}")
        raise

def download_instagram_video(url: str, out_path: str) -> str:
    """Скачиваем Instagram видео если прямая ссылка не работает"""
    if not check_cookies_file():
        raise FileNotFoundError("Файл cookies.txt не найден.")
    
    ydl_opts = {
        "outtmpl": os.path.join(out_path, "%(title).50s.%(ext)s"),
        "format": "best[ext=mp4]/best",
        "cookiefile": "cookies.txt",
        "quiet": True,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info)
    except Exception as e:
        logger.error(f"Ошибка скачивания Instagram: {e}")
        raise

def generate_task() -> str:
    if random.random() < 0.6:
        num1 = random.randint(100, 999)
        num2 = random.randint(100, 999)
        op = random.choice(["+", "-"])
        emoji = random.choice(["🧠", "🤯", "🤔", "🧮"])
        return f"{emoji} Пока ждёшь, попробуй решить:\n\n{num1} {op} {num2} = ?"
    else:
        riddles = [
            "🧩 Что тяжелее: килограмм ваты или килограмм железа?",
            "🤔 Сколько будет углов у квадрата, если отрезать один угол?",
            "🔄 Что всегда идёт, но никогда не приходит?",
            "🌍 У отца три сына: Чук, Гек и ... ?",
            "🔢 2 отца и 2 сына съели 3 яблока, и каждому досталось по целому. Как это возможно?",
            "🔢 Продолжи ряд: 2, 4, 6, 8, ... ?",
            "🧮 Что больше: половина от 8 или треть от 9?",
        ]
        return random.choice(riddles)

# ------------------------- хэндлеры -------------------------
@app.on_message(filters.command("start"))
async def start(_, message):
    await message.reply_text(
        "Привет! 👋\n\n"
        "📥 Отправь ссылку на Instagram — я скачаю видео для тебя.\n"
        "🎥 Или ссылку на YouTube — тоже скачаю видео.\n\n"
        "⚠️ Для Instagram требуется файл cookies.txt"
    )

@app.on_message(filters.text & ~filters.command("start"))
async def handle_text(_, message):
    text = message.text.strip()
    url = extract_first_url(text)
    if not url or not any(d in url for d in ["youtube.com", "youtu.be", "instagram.com"]):
        await message.delete()
        return

    status = await message.reply_text("⏳ Обработка видео...")
    try:
        url = normalize_url(url)
        
        if "youtube" in url or "youtu.be" in url:
            task_msg = await message.reply_text(generate_task())
            try:
                direct_url = await asyncio.to_thread(get_youtube_direct_url, url)
                await message.reply_video(direct_url, caption="📥 YouTube видео через @azams_bot")
            except BadRequest:
                tmp_dir = tempfile.mkdtemp()
                file_path = await asyncio.to_thread(download_youtube_video, url, tmp_dir)
                await message.reply_video(file_path, caption="📥 YouTube видео через @azams_bot")
                os.remove(file_path)
                os.rmdir(tmp_dir)
            await task_msg.delete()
            
        elif "instagram.com" in url:
            # ✅ Instagram с обработкой ошибок cookies
            if not os.path.exists("cookies.txt"):
                await status.edit_text("❌ Файл cookies.txt не найден. Instagram недоступен.")
                await asyncio.sleep(5)
                return
                
            try:
                direct_url = await asyncio.to_thread(get_instagram_url, url)
                await message.reply_video(direct_url, caption="📥 Instagram видео через @azams_bot")
            except Exception as e:
                await status.edit_text(f"❌ Ошибка Instagram: {e}")
                await asyncio.sleep(5)
                return

        await message.delete()
        await status.delete()
        
    except Exception as e:
        await status.edit_text(f"❌ Ошибка: {e}")
        await asyncio.sleep(5)
        await status.delete()

@app.on_message(filters.voice | filters.document | filters.audio | filters.sticker | filters.animation | filters.photo)
async def cleanup_messages(_, message):
    if message.photo:
        return
    await message.delete()
    await app.unpin_chat_message(chat_id=message.chat.id)

# ------------------------- запуск -------------------------
if __name__ == "__main__":
    # Удаляем старые файлы сессии перед запуском
    old_sessions = ["fast_bot.session", "fast_bot.session-journal"]
    for session_file in old_sessions:
        if os.path.exists(session_file):
            try:
                os.remove(session_file)
                logger.info(f"🗑️ Удален старый файл сессии: {session_file}")
            except Exception as e:
                logger.warning(f"Не удалось удалить {session_file}: {e}")
    
    # Проверяем cookies при запуске
    if os.path.exists("cookies.txt"):
        logger.info("✅ Файл cookies.txt найден - Instagram доступен")
    else:
        logger.warning("⚠️ Файл cookies.txt не найден - Instagram недоступен")
    
    logger.info("🚀 Запуск бота с новой сессией...")
    app.run()

