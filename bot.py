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

def download_youtube_video_enhanced(url: str, out_path: str) -> str:
    """Улучшенное скачивание YouTube с обходом ограничений"""
    ydl_opts = {
        "outtmpl": os.path.join(out_path, "%(title).100s.%(ext)s"),
        # Приоритетные форматы для обхода 403 ошибки
        "format": "best[height<=720][ext=mp4]/best[height<=480][ext=mp4]/best[ext=mp4]/best",
        "noplaylist": True,
        "quiet": False,
        "ignoreerrors": True,
        "retries": 10,
        "fragment_retries": 10,
        "skip_unavailable_fragments": True,
        "continue_dl": True,
        "no_overwrites": True,
        "merge_output_format": "mp4",
        # Настройки для обхода ограничений
        "throttled_rate": "100K",
        "http_chunk_size": 10485760,
        # Улучшенные заголовки
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.youtube.com/",
            "Origin": "https://www.youtube.com",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
        },
        # Настройки для YouTube
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web"],
                "player_skip": ["configs", "webpage"],
            }
        },
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Задержка перед началом скачивания
            time.sleep(random.uniform(1, 3))
            
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
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

def download_youtube_video_simple(url: str, out_path: str) -> str:
    """Простой метод скачивания для сложных случаев"""
    ydl_opts = {
        "outtmpl": os.path.join(out_path, "%(title).100s.%(ext)s"),
        # Самые простые форматы
        "format": "worst[ext=mp4]/worstvideo[ext=mp4]+worstaudio/best[height<=360]",
        "noplaylist": True,
        "quiet": False,
        "ignoreerrors": True,
        "retries": 15,
        "fragment_retries": 15,
        "skip_unavailable_fragments": True,
        "continue_dl": True,
        "no_overwrites": True,
        "merge_output_format": "mp4",
        # Медленная скорость для обхода блокировок
        "throttled_rate": "50K",
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.5",
        },
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Большая задержка для простого метода
            time.sleep(random.uniform(3, 5))
            
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            if not os.path.exists(filename):
                raise Exception(f"Файл не создан: {filename}")
                
            file_size = os.path.getsize(filename)
            if file_size == 0:
                os.remove(filename)
                raise Exception(f"Файл пустой: {filename}")
                
            logger.info(f"✅ YouTube видео скачано (простой метод): {filename}")
            return filename
            
    except Exception as e:
        logger.error(f"❌ Ошибка простого метода: {e}")
        raise

def try_youtube_download(url: str, out_path: str) -> str:
    """Пробуем разные методы скачивания YouTube"""
    methods = [
        ("Улучшенный метод", download_youtube_video_enhanced),
        ("Простой метод", download_youtube_video_simple),
    ]
    
    last_error = None
    
    for method_name, method_func in methods:
        try:
            logger.info(f"🔄 Пробую {method_name}...")
            return method_func(url, out_path)
        except Exception as e:
            last_error = e
            logger.warning(f"❌ {method_name} не сработал: {e}")
            time.sleep(2)
            continue
    
    raise Exception(f"Все методы YouTube не сработали. Последняя ошибка: {last_error}")

# ------------------------- INSTAGRAM ФУНКЦИИ -------------------------

def check_cookies_file():
    if not os.path.exists("cookies.txt"):
        return False
    return os.path.getsize("cookies.txt") > 0

def try_instagram_download(url: str, out_path: str):
    """Пробуем скачать Instagram"""
    if not check_cookies_file():
        raise Exception("Требуется файл cookies.txt")
    
    ydl_opts = {
        "outtmpl": os.path.join(out_path, "instagram_%(title)s.%(ext)s"),
        "cookiefile": "cookies.txt",
        "quiet": False,
        "ignoreerrors": True,
        "retries": 3,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            for file in os.listdir(out_path):
                file_path = os.path.join(out_path, file)
                if os.path.isfile(file_path) and os.path.getsize(file_path) > 0:
                    return file_path, info
            
            raise Exception("Не удалось скачать Instagram контент")
            
    except Exception as e:
        raise Exception(f"Instagram ошибка: {e}")

# ------------------------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ -------------------------

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

def get_media_type(file_path: str) -> str:
    """Определяем тип медиа по расширению файла"""
    if not file_path:
        return "unknown"
    
    ext = file_path.lower().split('.')[-1]
    
    if ext in ['mp4', 'webm', 'mkv', 'mov', 'avi']:
        return "video"
    elif ext in ['jpg', 'jpeg', 'png', 'webp', 'gif']:
        return "photo"
    else:
        return "unknown"

async def safe_send_video(client, chat_id, file_path, caption=""):
    """Безопасная отправка видео"""
    try:
        if not os.path.exists(file_path):
            raise Exception(f"Файл не существует: {file_path}")
            
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            raise Exception(f"Файл пустой: {file_path}")
            
        return await client.send_video(
            chat_id=chat_id,
            video=file_path,
            caption=caption,
            supports_streaming=True
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка отправки видео: {e}")
        raise

async def safe_send_photo(client, chat_id, file_path, caption=""):
    """Безопасная отправка фото"""
    try:
        if not os.path.exists(file_path):
            raise Exception(f"Файл не существует: {file_path}")
            
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            raise Exception(f"Файл пустой: {file_path}")
            
        return await client.send_photo(
            chat_id=chat_id,
            photo=file_path,
            caption=caption
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка отправки фото: {e}")
        raise

# ------------------------- ОБРАБОТЧИКИ -------------------------

@app.on_message(filters.command("start"))
async def start(client, message):
    message_id = f"start_{message.id}_{message.from_user.id}"
    
    if message_id in processed_messages:
        return
        
    processed_messages.add(message_id)
    
    await message.reply_text(
        "🎥 **YouTube Video Downloader**\n\n"
        "📥 Отправьте ссылку на YouTube видео и я скачаю его для вас!\n\n"
        "✅ **Поддерживается:**\n"
        "• YouTube видео любого качества\n"
        "• YouTube Shorts\n"
        "• Музыкальные клипы\n\n"
        "⚡ Быстрое и надежное скачивание!\n"
        "🔄 Автоперезапуск каждые 12 часов"
    )

@app.on_message(filters.command(["help", "info"]))
async def help_command(client, message):
    message_id = f"help_{message.id}_{message.from_user.id}"
    
    if message_id in processed_messages:
        return
        
    processed_messages.add(message_id)
    
    await message.reply_text(
        "🤖 **Помощь по YouTube боту**\n\n"
        "🎥 **Как использовать:**\n"
        "1. Найдите видео на YouTube\n"
        "2. Скопируйте ссылку из адресной строки\n"
        "3. Отправьте ссылку боту\n"
        "4. Получите скачанное видео!\n\n"
        "📹 **Поддерживаемые форматы:**\n"
        "• Видео до 720p качества\n"
        "• Короткие видео (Shorts)\n"
        "• Длинные видео\n\n"
        "⚡ Просто отправьте ссылку и наслаждайтесь!"
    )

@app.on_message(filters.command("test"))
async def test_command(client, message):
    """Тест работоспособности"""
    await message.reply_text(
        "🧪 **Тест YouTube бота**\n\n"
        "Бот готов к работе! 🎉\n\n"
        "Отправьте любую ссылку на YouTube видео для проверки.\n"
        "Например: https://www.youtube.com/watch?v=dQw4w9WgXcQ"
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
    if not url:
        return

    # Поддерживаем только YouTube
    if not any(domain in url for domain in ["youtube.com", "youtu.be"]):
        await message.reply_text(
            "❌ Поддерживаются только YouTube ссылки\n\n"
            "🎥 Пожалуйста, отправьте ссылку на:\n"
            "• YouTube видео (youtube.com/watch?v=...)\n"
            "• YouTube Shorts (youtube.com/shorts/...)\n"
            "• Сокращенная ссылка (youtu.be/...)\n\n"
            "⚡ YouTube работает быстро и надежно!"
        )
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
        status = await message.reply_text("⏳ Обработка YouTube ссылки...")
        
        # Только YouTube обработка
        tmp_dir = tempfile.mkdtemp()
        file_path = None
        
        try:
            await status.edit_text("🔍 Анализирую видео...")
            
            # Пробуем скачать YouTube
            file_path = await asyncio.to_thread(try_youtube_download, url, tmp_dir)
            
            await status.edit_text("📤 Отправляю видео...")
            
            await safe_send_video(
                client,
                message.chat.id,
                file_path,
                caption="📥 YouTube видео скачано через @azams_bot"
            )
            logger.info("✅ YouTube видео успешно отправлено")

        except Exception as e:
            logger.error(f"❌ YouTube ошибка: {e}")
            
            # Конкретные сообщения для разных ошибок
            error_msg = str(e)
            if "403" in error_msg:
                user_msg = (
                    "❌ YouTube временно ограничил доступ\n\n"
                    "🔧 **Что можно сделать:**\n"
                    "• Попробуйте другую ссылку\n"
                    "• Подождите несколько минут\n"
                    "• Попробуйте видео с другим качеством\n\n"
                    "⚡ Обычно это временное ограничение"
                )
            elif "Private" in error_msg or "private" in error_msg:
                user_msg = "❌ Это приватное видео. Доступ ограничен."
            elif "Unavailable" in error_msg:
                user_msg = "❌ Видео недоступно или удалено."
            elif "too long" in error_msg.lower():
                user_msg = "❌ Видео слишком длинное. Попробуйте shorter video."
            else:
                user_msg = f"❌ Не удалось скачать видео\n\nПричина: {error_msg}"
            
            raise Exception(user_msg)
            
        finally:
            # Очистка
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
            if os.path.exists(tmp_dir):
                try:
                    for file in os.listdir(tmp_dir):
                        os.remove(os.path.join(tmp_dir, file))
                    os.rmdir(tmp_dir)
                except:
                    pass

        # Успешное завершение
        await message.delete()

    except Exception as e:
        logger.error(f"❌ Ошибка обработки для пользователя {user_id}: {e}")
        
        if status:
            try:
                error_msg = await message.reply_text(str(e))
                await asyncio.sleep(10)
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
    
    logger.info("🚀 Запуск YouTube бота с улучшенной обработкой 403 ошибок...")
    logger.info("🎥 Бот готов к скачиванию YouTube видео!")
    app.run()
