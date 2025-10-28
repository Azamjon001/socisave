import os
import asyncio
import logging
import tempfile
import yt_dlp
import re
import time
from pyrogram import Client, filters
from pyrogram.errors import BadRequest, BadMsgNotification

API_ID = 26670278
API_HASH = "e3d77390fd9c22d98bb6bddca86fef1a"
BOT_TOKEN = "6788128988:AAEMmCSafiiEqtS5UWQQxfo--W0On7B6Q08"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Глобальные переменные
user_processing = {}
processed_messages = set()

class SafeClient(Client):
    async def send(self, *args, **kwargs):
        for attempt in range(3):
            try:
                return await super().send(*args, **kwargs)
            except BadMsgNotification as e:
                if e.error_code == 16:
                    logger.warning(f"BadMsgNotification [16], попытка {attempt + 1}/3")
                    self.session.msg_id_offset = int(time.time() * 2**32)
                    await asyncio.sleep(1)
                else:
                    raise
        raise RuntimeError("Не удалось синхронизировать msg_id с Telegram")

app = SafeClient(
    "video_bot_new_session_2024",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    sleep_threshold=15
)

# ------------------------- ИСПРАВЛЕННЫЕ YOUTUBE ФУНКЦИИ -------------------------

def get_youtube_direct_url(url: str) -> str:
    """Получаем прямую ссылку на YouTube видео с обходом ограничений"""
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "format": "best[height<=720][ext=mp4]/best[ext=mp4]/best",
        "noplaylist": True,
        # Обходные пути для YouTube
        "extract_flat": False,
        "ignoreerrors": True,
        "no_warnings": False,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-us,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Charset": "ISO-8859-1,utf-8;q=0.7,*;q=0.7",
            "Connection": "keep-alive",
        }
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Пытаемся найти прямую ссылку
            if 'url' in info:
                return info['url']
            
            # Или ищем в форматах
            elif 'formats' in info:
                formats = info['formats']
                
                # Сначала ищем mp4 с высотой <= 720p
                mp4_formats = [f for f in formats if f.get('ext') == 'mp4' and f.get('height', 0) <= 720 and f.get('url')]
                if mp4_formats:
                    # Выбираем лучший качественный формат
                    best_format = max(mp4_formats, key=lambda x: x.get('height', 0))
                    return best_format['url']
                
                # Если нет mp4, берем любой доступный формат
                available_formats = [f for f in formats if f.get('url')]
                if available_formats:
                    best_format = max(available_formats, key=lambda x: x.get('height', 0))
                    return best_format['url']
            
            raise Exception("Не удалось получить прямую ссылку на видео")
            
    except Exception as e:
        logger.error(f"Ошибка получения YouTube URL: {e}")
        raise

def download_youtube_video(url: str, out_path: str) -> str:
    """Скачиваем YouTube видео с улучшенными настройками"""
    ydl_opts = {
        "outtmpl": os.path.join(out_path, "%(title).50s.%(ext)s"),
        "format": "best[height<=720][ext=mp4]/best[ext=mp4]/best",
        "noplaylist": True,
        "quiet": False,  # Включаем логи для отладки
        "retries": 3,
        "fragment_retries": 3,
        "skip_unavailable_fragments": True,
        "merge_output_format": "mp4",
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Language": "en-us,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
        },
        # Обходные пути для signature extraction
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web"],
                "player_skip": ["configs", "webpage"]
            }
        }
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            logger.info(f"✅ YouTube видео скачано: {filename}")
            return filename
    except Exception as e:
        logger.error(f"❌ Ошибка скачивания YouTube: {e}")
        raise

# ------------------------- ОСТАЛЬНЫЕ ФУНКЦИИ БЕЗ ИЗМЕНЕНИЙ -------------------------

def extract_first_url(text: str) -> str:
    match = re.search(r"(https?://[^\s]+)", text)
    return match.group(1) if match else ""

def normalize_url(url: str) -> str:
    if "youtu.be/" in url:
        video_id = url.split("/")[-1].split("?")[0]
        return f"https://www.youtube.com/watch?v={video_id}"
    return url

def check_cookies_file():
    if not os.path.exists("cookies.txt"):
        logger.error("❌ Файл cookies.txt не найден!")
        return False
    logger.info("✅ Файл cookies.txt найден")
    return True

def get_instagram_url(url: str) -> str:
    if not check_cookies_file():
        raise FileNotFoundError("Файл cookies.txt не найден.")
    
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "format": "best[ext=mp4]/best",
        "cookiefile": "cookies.txt",
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return info.get("url")

def download_instagram_video(url: str, out_path: str) -> str:
    if not check_cookies_file():
        raise FileNotFoundError("Файл cookies.txt не найден.")
    
    ydl_opts = {
        "outtmpl": os.path.join(out_path, "%(title).50s.%(ext)s"),
        "format": "best[ext=mp4]/best",
        "cookiefile": "cookies.txt",
        "quiet": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)

# ------------------------- ОБРАБОТЧИКИ -------------------------

@app.on_message(filters.command("start"))
async def start(client, message):
    message_id = f"start_{message.id}_{message.from_user.id}"
    
    if message_id in processed_messages:
        return
        
    processed_messages.add(message_id)
    
    await message.reply_text(
        "Привет! 👋\n\n"
        "📥 Отправь ссылку на Instagram или YouTube — я скачаю видео для тебя.\n\n"
        "⚡ Бот автоматически перезапускается каждые 12 часов для стабильной работы!"
    )

@app.on_message(filters.command(["help", "info"]))
async def help_command(client, message):
    message_id = f"help_{message.id}_{message.from_user.id}"
    
    if message_id in processed_messages:
        return
        
    processed_messages.add(message_id)
    
    await message.reply_text(
        "🤖 **Помощь по боту**\n\n"
        "📥 Просто отправь ссылку на:\n"
        "• Instagram видео/реельс\n" 
        "• YouTube видео\n\n"
        "⚡ Скачивание работает быстро и бесплатно!\n"
        "🔄 Бот перезапускается каждые 12 часов"
    )

@app.on_message(filters.text & filters.private)
async def handle_text(client, message):
    if message.text.startswith('/'):
        return
    
    message_id = f"text_{message.id}_{message.from_user.id}"
    
    if message_id in processed_messages:
        return
        
    user_id = message.from_user.id
    text = message.text.strip()
    
    url = extract_first_url(text)
    if not url or not any(d in url for d in ["youtube.com", "youtu.be", "instagram.com"]):
        return

    processed_messages.add(message_id)
    
    if user_id in user_processing and user_processing[user_id].get('processing'):
        temp_msg = await message.reply_text("⏳ Ваш предыдущий запрос еще обрабатывается...")
        await asyncio.sleep(3)
        await temp_msg.delete()
        processed_messages.discard(message_id)
        return

    user_processing[user_id] = {'processing': True}
    status = None
    
    try:
        url = normalize_url(url)
        status = await message.reply_text("⏳ Обработка видео...")
        
        if "youtube" in url or "youtu.be" in url:
            try:
                await status.edit_text("🔗 Получаю прямую ссылку YouTube...")
                direct_url = await asyncio.to_thread(get_youtube_direct_url, url)
                
                await status.edit_text("📤 Отправляю видео...")
                await message.reply_video(
                    direct_url, 
                    caption="📥 YouTube видео скачано через @azams_bot"
                )
                logger.info("✅ YouTube видео отправлено через прямую ссылку")
                
            except Exception as e:
                logger.warning(f"❌ Прямая ссылка YouTube не сработала: {e}, скачиваю файл...")
                await status.edit_text("📥 Скачиваю YouTube видео...")
                tmp_dir = tempfile.mkdtemp()
                
                try:
                    file_path = await asyncio.to_thread(download_youtube_video, url, tmp_dir)
                    await status.edit_text("📤 Отправляю видео...")
                    await message.reply_video(
                        file_path, 
                        caption="📥 YouTube видео скачано через @azams_bot"
                    )
                    logger.info("✅ YouTube видео отправлено как файл")
                    
                    # Очистка временных файлов
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    os.rmdir(tmp_dir)
                    
                except Exception as download_error:
                    # Очистка при ошибке
                    if os.path.exists(tmp_dir):
                        for file in os.listdir(tmp_dir):
                            os.remove(os.path.join(tmp_dir, file))
                        os.rmdir(tmp_dir)
                    raise download_error
                
        elif "instagram.com" in url:
            if not os.path.exists("cookies.txt"):
                await status.edit_text("❌ Файл cookies.txt не найден.")
                await asyncio.sleep(5)
                await status.delete()
                return
                
            try:
                await status.edit_text("🔗 Получаю прямую ссылку Instagram...")
                direct_url = await asyncio.to_thread(get_instagram_url, url)
                if direct_url:
                    await status.edit_text("📤 Отправляю видео...")
                    await message.reply_video(
                        direct_url, 
                        caption="📥 Instagram видео скачано через @azams_bot"
                    )
                    logger.info("✅ Instagram видео отправлено через прямую ссылку")
                else:
                    raise Exception("Не удалось получить прямую ссылку")
                
            except Exception as e:
                logger.warning(f"❌ Прямая ссылка Instagram не сработала: {e}, скачиваю файл...")
                await status.edit_text("📥 Скачиваю Instagram видео...")
                tmp_dir = tempfile.mkdtemp()
                
                try:
                    file_path = await asyncio.to_thread(download_instagram_video, url, tmp_dir)
                    await status.edit_text("📤 Отправляю видео...")
                    await message.reply_video(
                        file_path,
                        caption="📥 Instagram видео скачано через @azams_bot"
                    )
                    logger.info("✅ Instagram видео отправлено как файл")
                    
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    os.rmdir(tmp_dir)
                    
                except Exception as download_error:
                    if os.path.exists(tmp_dir):
                        for file in os.listdir(tmp_dir):
                            os.remove(os.path.join(tmp_dir, file))
                        os.rmdir(tmp_dir)
                    raise download_error

        # Успешное завершение
        await message.delete()

    except Exception as e:
        logger.error(f"❌ Ошибка обработки для пользователя {user_id}: {e}")
        
        if status:
            try:
                error_msg = await message.reply_text(f"❌ Ошибка: Не удалось обработать видео. Попробуйте другую ссылку.")
                await asyncio.sleep(5)
                await error_msg.delete()
            except:
                pass
                
    finally:
        if status:
            try:
                await status.delete()
            except:
                pass
        if user_id in user_processing:
            user_processing[user_id]['processing'] = False

# ------------------------- ЗАПУСК -------------------------
if __name__ == "__main__":
    # Очистка старых сессий
    old_sessions = ["fast_bot.session", "fast_bot.session-journal"]
    for session_file in old_sessions:
        if os.path.exists(session_file):
            try:
                os.remove(session_file)
                logger.info(f"🗑️ Удален старый файл сессии: {session_file}")
            except Exception as e:
                logger.warning(f"Не удалось удалить {session_file}: {e}")
    
    # Проверка cookies
    if os.path.exists("cookies.txt"):
        logger.info("✅ Файл cookies.txt найден")
    else:
        logger.warning("⚠️ Файл cookies.txt не найден")
    
    logger.info("🚀 Запуск бота с исправленным YouTube...")
    app.run()
