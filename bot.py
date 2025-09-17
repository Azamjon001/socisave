



import os
import asyncio
import logging
import tempfile
import yt_dlp
import re
import random
from pyrogram import Client, filters
from pyrogram.errors import BadRequest

API_ID = 29683541
API_HASH = "3a9d6a1205003b0145bc9b6b8d8e1193"
BOT_TOKEN = "7482941211:AAEpXEnHeFVAh8mq8EhdHowsD2RNEpnP4WM"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация клиента Pyrogram
app = Client(
    "fast_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# -------------------------
# Вспомогательные функции
# -------------------------
def extract_first_url(text: str) -> str:
    match = re.search(r"(https?://[^\s]+)", text)
    return match.group(1) if match else ""

def normalize_url(url: str) -> str:
    if "youtu.be/" in url:
        video_id = url.split("/")[-1].split("?")[0]
        return f"https://www.youtube.com/watch?v={video_id}"
    return url

def get_youtube_direct_url(url: str) -> str:
    """Получить прямую ссылку на YouTube-видео"""
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "format": "mp4[height<=720]/best[ext=mp4]/best",
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return info.get("url")

def download_youtube_video(url: str, out_path: str) -> str:
    """Скачать видео с YouTube (fallback режим)"""
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
    """Получить прямую ссылку на Instagram-видео"""
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "format": "best[ext=mp4]/best",
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return info.get("url")

# -------------------------
# Генерация развлечений
# -------------------------
def generate_task() -> str:
    """Рандомная задачка: математика или загадка"""
    if random.random() < 0.6:  # 60% шанс на математику
        num1 = random.randint(100, 999)
        num2 = random.randint(100, 999)
        op = random.choice(["+", "-"])
        emoji = random.choice(["🧠", "🤯", "🤔", "🧮"])
        return f"{emoji} Пока ждёшь, попробуй решить:\n\n{num1} {op} {num2} = ?"
    else:  # 40% шанс на загадку
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

# -------------------------
# Хэндлеры
# -------------------------
@app.on_message(filters.command("start"))
async def start(_, message):
    await message.reply_text(
        "Привет! 👋\n\n"
        "📥 Отправь ссылку на YouTube или Instagram — Я буду скачивать его для вас\n"
    )

@app.on_message(filters.text & ~filters.command("start"))
async def handle_text(_, message):
    text = message.text.strip()
    url = extract_first_url(text)

    if not url or not any(domain in url for domain in ["youtube.com", "youtu.be", "instagram.com"]):
        await message.delete()
        await message.reply_text("⚠️ Это не ссылка YouTube или Instagram")
        return

    status = await message.reply_text("⏳ Обработка видео...")

    try:
        url = normalize_url(url)

        if "youtube" in url or "youtu.be" in url:
            # 🔹 Отправляем развлечение
            task_msg = await message.reply_text(generate_task())

            try:
                # --- YouTube: пробуем стриминг ---
                direct_url = await asyncio.to_thread(get_youtube_direct_url, url)
                await message.reply_video(direct_url, caption="📥 YouTube видео через @aco007_BOT")
            except BadRequest:
                # --- Если стрим не сработал — fallback на скачивание ---
                tmp_dir = tempfile.mkdtemp()
                file_path = await asyncio.to_thread(download_youtube_video, url, tmp_dir)
                await message.reply_video(file_path, caption="📥 YouTube видео через @aco007_BOT")
                os.remove(file_path)
                os.rmdir(tmp_dir)

            # Удаляем сообщение с задачкой
            await task_msg.delete()

        elif "instagram.com" in url:
            # --- Instagram: только стриминг ---
            direct_url = await asyncio.to_thread(get_instagram_url, url)
            await message.reply_video(direct_url, caption="📥 Instagram видео через @aco007_BOT")

        await message.delete()
        await status.delete()

    except Exception as e:
        await status.edit_text(f"❌ Ошибка: {e}")

@app.on_message(filters.voice)
async def handle_voice(_, message):
    await message.delete()
    await message.reply_text("⚠️ Это не ссылка YouTube или Instagram")

# -------------------------
# Запуск
# -------------------------
if __name__ == "__main__":
    app.run()







