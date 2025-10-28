import os
import asyncio
import logging
import tempfile
import yt_dlp
import re
import time
import random
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
    """Получаем прямую ссылку на YouTube видео"""
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "format": "best[height<=480][ext=mp4]/best[height<=720][ext=mp4]/best[ext=mp4]/best",
        "noplaylist": True,
        "ignoreerrors": True,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if not info:
                raise Exception("Не удалось получить информацию о видео")
                
            if 'url' in info:
                return info['url']
            
            elif 'formats' in info:
                formats = info['formats']
                available_formats = [f for f in formats if f.get('url') and f.get('ext') == 'mp4']
                if available_formats:
                    available_formats.sort(key=lambda x: x.get('height', 0))
                    for fmt in available_formats:
                        if fmt.get('height', 0) <= 480:
                            return fmt['url']
                    return available_formats[0]['url']
            
            raise Exception("Не удалось получить прямую ссылку")
            
    except Exception as e:
        logger.error(f"Ошибка получения YouTube URL: {e}")
        raise

def download_youtube_video(url: str, out_path: str) -> str:
    """Скачиваем YouTube видео с проверкой файла"""
    ydl_opts = {
        "outtmpl": os.path.join(out_path, "%(title).100s.%(ext)s"),
        "format": "best[height<=480][ext=mp4]/best[height<=720][ext=mp4]/best[ext=mp4]/best",
        "noplaylist": True,
        "quiet": False,
        "ignoreerrors": True,
        "retries": 5,
        "fragment_retries": 5,
        "skip_unavailable_fragments": True,
        "continue_dl": True,
        "no_overwrites": True,
        "merge_output_format": "mp4",
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            time.sleep(random.uniform(1, 2))
            
            info = ydl.extract_info(url, download=True)
            if not info:
                raise Exception("Не удалось скачать видео")
                
            filename = ydl.prepare_filename(info)
            
            # ПРОВЕРЯЕМ ЧТО ФАЙЛ СУЩЕСТВУЕТ И НЕ ПУСТОЙ
            if not os.path.exists(filename):
                raise Exception(f"Файл не создан: {filename}")
                
            file_size = os.path.getsize(filename)
            if file_size == 0:
                os.remove(filename)
                raise Exception(f"Файл пустой: {filename}")
                
            logger.info(f"✅ YouTube видео скачано: {filename} ({file_size} bytes)")
            return filename
            
    except Exception as e:
        logger.error(f"❌ Ошибка скачивания YouTube: {e}")
        raise

def safe_send_video(client, chat_id, file_path, caption=""):
    """Безопасная отправка видео с проверками"""
    try:
        # Проверяем что файл существует и не пустой
        if not os.path.exists(file_path):
            raise Exception(f"Файл не существует: {file_path}")
            
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            raise Exception(f"Файл пустой: {file_path}")
            
        # Проверяем размер файла (Telegram ограничение ~2GB)
        if file_size > 1900 * 1024 * 1024:  # 1.9GB
            raise Exception("Файл слишком большой для Telegram")
            
        # Отправляем видео
        return client.send_video(
            chat_id=chat_id,
            video=file_path,
            caption=caption,
            supports_streaming=True
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка отправки видео: {e}")
        raise

# ------------------------- ОСТАЛЬНЫЕ ФУНКЦИИ -------------------------

def extract_first_url(text: str) -> str:
    match = re.search(r"(https?://[^\s]+)", text)
    return match.group(1) if match else ""

def normalize_url(url: str) -> str:
    if "youtu.be/" in url:
        video_id = url.split("/")[-1].split("?")[0]
        return f"https://www.youtube.com/watch?v={video_id}"
    if "youtube.com/shorts/" in url:
        video_id = url.split("/shorts/")[-1].split("?")[0]
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
        "outtmpl": os.path.join(out_path, "%(title).100s.%(ext)s"),
        "format": "best[ext=mp4]/best",
        "cookiefile": "cookies.txt",
        "quiet": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        
        # Проверяем файл
        if not os.path.exists(filename):
            raise Exception(f"Файл Instagram не создан: {filename}")
            
        file_size = os.path.getsize(filename)
        if file_size == 0:
            os.remove(filename)
            raise Exception(f"Файл Instagram пустой: {filename}")
            
        return filename

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
        "⚡ Поддерживаются YouTube Shorts!\n"
        "🔄 Бот перезапускается каждые 12 часов"
    )

@app.on_message(filters.command(["help", "info"]))
async def help_command(client, message):
    message_id = f"help_{message.id}_{message.from_user.id}"
    
    if message_id in processed_messages:
        return
        
    processed_messages.add(message_id)
    
    await message.reply_text(
        "🤖 **Помощь по боту**\n\n"
        "📥 Поддерживаемые ссылки:\n"
        "• Instagram видео/реельс\n" 
        "• YouTube видео\n"
        "• YouTube Shorts\n\n"
        "⚡ Скачивание работает быстро и бесплатно!"
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
            # YouTube обработка
            tmp_dir = tempfile.mkdtemp()
            file_path = None
            
            try:
                # Пробуем прямую ссылку
                await status.edit_text("🔗 Получаю прямую ссылку YouTube...")
                try:
                    direct_url = await asyncio.to_thread(get_youtube_direct_url, url)
                    await status.edit_text("📤 Отправляю видео...")
                    await message.reply_video(
                        direct_url, 
                        caption="📥 YouTube видео скачано через @azams_bot"
                    )
                    logger.info("✅ YouTube видео отправлено через прямую ссылку")
                    
                except Exception as e:
                    logger.warning(f"❌ Прямая ссылка не сработала: {e}, скачиваю файл...")
                    await status.edit_text("📥 Скачиваю YouTube видео...")
                    
                    # Скачиваем файл
                    file_path = await asyncio.to_thread(download_youtube_video, url, tmp_dir)
                    
                    # Проверяем файл перед отправкой
                    if not os.path.exists(file_path):
                        raise Exception("Файл не был создан после скачивания")
                        
                    file_size = os.path.getsize(file_path)
                    logger.info(f"📊 Размер файла: {file_size} bytes")
                    
                    await status.edit_text("📤 Отправляю видео...")
                    
                    # Используем безопасную отправку
                    await safe_send_video(
                        client,
                        message.chat.id,
                        file_path,
                        caption="📥 YouTube видео скачано через @azams_bot"
                    )
                    logger.info("✅ YouTube видео отправлено как файл")

            finally:
                # ОЧИСТКА В ЛЮБОМ СЛУЧАЕ
                if file_path and os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                        logger.info(f"🗑️ Удален временный файл: {file_path}")
                    except Exception as e:
                        logger.warning(f"Не удалось удалить файл {file_path}: {e}")
                
                if os.path.exists(tmp_dir):
                    try:
                        # Удаляем оставшиеся файлы в папке
                        for file in os.listdir(tmp_dir):
                            file_to_remove = os.path.join(tmp_dir, file)
                            if os.path.exists(file_to_remove):
                                os.remove(file_to_remove)
                        os.rmdir(tmp_dir)
                        logger.info(f"🗑️ Удалена временная папка: {tmp_dir}")
                    except Exception as e:
                        logger.warning(f"Не удалось удалить папку {tmp_dir}: {e}")
                
        elif "instagram.com" in url:
            # Instagram обработка
            if not os.path.exists("cookies.txt"):
                await status.edit_text("❌ Файл cookies.txt не найден.")
                await asyncio.sleep(5)
                await status.delete()
                return
                
            tmp_dir = tempfile.mkdtemp()
            file_path = None
            
            try:
                await status.edit_text("🔗 Получаю прямую ссылку Instagram...")
                try:
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
                    
                    file_path = await asyncio.to_thread(download_instagram_video, url, tmp_dir)
                    
                    # Проверяем файл
                    if not os.path.exists(file_path):
                        raise Exception("Файл Instagram не создан")
                        
                    await status.edit_text("📤 Отправляю видео...")
                    
                    await safe_send_video(
                        client,
                        message.chat.id,
                        file_path,
                        caption="📥 Instagram видео скачано через @azams_bot"
                    )
                    logger.info("✅ Instagram видео отправлено как файл")

            finally:
                # Очистка для Instagram
                if file_path and os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except:
                        pass
                
                if os.path.exists(tmp_dir):
                    try:
                        for file in os.listdir(tmp_dir):
                            file_to_remove = os.path.join(tmp_dir, file)
                            if os.path.exists(file_to_remove):
                                os.remove(file_to_remove)
                        os.rmdir(tmp_dir)
                    except:
                        pass

        # Успешное завершение
        await message.delete()

    except Exception as e:
        logger.error(f"❌ Ошибка обработки для пользователя {user_id}: {e}")
        
        if status:
            try:
                error_msg = await message.reply_text(
                    f"❌ Ошибка: {str(e)[:100]}...\n\n"
                    "📥 Попробуйте другую ссылку или обратитесь к администратору."
                )
                await asyncio.sleep(8)
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
    
    logger.info("🚀 Запуск бота с исправленной обработкой файлов...")
    app.run()
