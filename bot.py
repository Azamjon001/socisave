import os
import asyncio
import logging
import tempfile
import yt_dlp
import re
import random
import time
from pyrogram import Client, filters
from pyrogram.errors import BadRequest, BadMsgNotification

API_ID = 29683541
API_HASH = "3a9d6a1205003b0145bc9b6b8d8e1193"
BOT_TOKEN = "6788128988:AAF1lnBqcl1PDDuTw7ONKXrUpNfR1oh4Ggw"

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

def get_instagram_url(url: str) -> str:
    ydl_opts = {"quiet": True, "skip_download": True, "format": "best[ext=mp4]/best"}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return info.get("url")

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


ydl_opts = {
    'outtmpl': 'downloads/%(title)s.%(ext)s',
    'cookies': 'cookies.txt',
    'http_headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
    }
}



# ------------------------- хэндлеры -------------------------
@app.on_message(filters.command("start"))
async def start(_, message):
    await message.reply_text(
        "Привет! 👋\n\n"
        "📥 Отправь ссылку на Instagram — Я буду скачивать его для вас\n"
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
            direct_url = await asyncio.to_thread(get_instagram_url, url)
            await message.reply_video(direct_url, caption="📥 Instagram видео через @azams_bot")

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
    app.run()


