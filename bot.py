import os
import asyncio
import logging
import tempfile
import yt_dlp
import re
import time
import random
import requests
from pyrogram import Client, filters
from pyrogram.errors import BadRequest, BadMsgNotification
from pyrogram.types import InputMediaPhoto

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

# ------------------------- YOUTUBE ФУНКЦИИ -------------------------

def get_youtube_info(url: str):
    """Получаем информацию о видео"""
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "noplaylist": True,
        "ignoreerrors": True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception as e:
        logger.error(f"Ошибка получения информации: {e}")
        raise

def download_youtube_video_best(url: str, out_path: str) -> str:
    """Лучший метод скачивания YouTube"""
    ydl_opts = {
        "outtmpl": os.path.join(out_path, "%(title).100s.%(ext)s"),
        "format": "best[height<=720]/best",
        "noplaylist": True,
        "quiet": False,
        "ignoreerrors": True,
        "retries": 10,
        "fragment_retries": 10,
        "skip_unavailable_fragments": True,
        "continue_dl": True,
        "no_overwrites": True,
        "merge_output_format": "mp4",
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
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

# ------------------------- INSTAGRAM ФУНКЦИИ (ПЕРЕПИСАННЫЕ) -------------------------

def check_cookies_file():
    if not os.path.exists("cookies.txt"):
        logger.error("❌ Файл cookies.txt не найден!")
        return False
    logger.info("✅ Файл cookies.txt найден")
    return True

def download_instagram_simple(url: str, out_path: str):
    """Простой метод скачивания Instagram с принудительным форматом"""
    if not check_cookies_file():
        raise FileNotFoundError("Файл cookies.txt не найден.")
    
    ydl_opts = {
        "outtmpl": os.path.join(out_path, "%(title).100s.%(ext)s"),
        "cookiefile": "cookies.txt",
        "quiet": False,
        "ignoreerrors": True,
        "retries": 3,
        "format": "best",  # Принудительно используем лучший формат
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            if not info:
                raise Exception("Не удалось получить информацию о контенте")
            
            filename = ydl.prepare_filename(info)
            
            # Проверяем разные возможные имена файлов
            possible_files = [
                filename,
                filename.replace('.webm', '.mp4').replace('.mkv', '.mp4'),
                os.path.join(out_path, f"{info.get('title', 'instagram_media')}.mp4"),
                os.path.join(out_path, f"{info.get('title', 'instagram_media')}.jpg"),
            ]
            
            actual_file = None
            for file_path in possible_files:
                if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                    actual_file = file_path
                    break
            
            if not actual_file:
                # Ищем любой файл в папке
                for file in os.listdir(out_path):
                    file_path = os.path.join(out_path, file)
                    if os.path.isfile(file_path) and os.path.getsize(file_path) > 0:
                        actual_file = file_path
                        break
            
            if not actual_file:
                raise Exception("Не удалось найти скачанный файл")
                
            logger.info(f"✅ Instagram медиа скачано: {actual_file}")
            return actual_file, info
            
    except Exception as e:
        logger.error(f"Ошибка скачивания Instagram: {e}")
        raise

def download_instagram_direct(url: str, out_path: str):
    """Прямое скачивание Instagram без сложных форматов"""
    if not check_cookies_file():
        raise FileNotFoundError("Файл cookies.txt не найден.")
    
    ydl_opts = {
        "outtmpl": os.path.join(out_path, "instagram_media.%(ext)s"),
        "cookiefile": "cookies.txt",
        "quiet": False,
        "ignoreerrors": True,
        "retries": 5,
        "fragment_retries": 5,
        "skip_unavailable_fragments": True,
        "extract_flat": False,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            # Ищем скачанный файл
            for file in os.listdir(out_path):
                file_path = os.path.join(out_path, file)
                if os.path.isfile(file_path) and os.path.getsize(file_path) > 0:
                    logger.info(f"✅ Найден файл: {file_path} ({os.path.getsize(file_path)} bytes)")
                    return file_path, info
            
            raise Exception("Не удалось найти скачанный файл")
            
    except Exception as e:
        logger.error(f"Ошибка прямого скачивания Instagram: {e}")
        raise

def get_instagram_media_type(file_path: str, info: dict) -> str:
    """Определяем тип медиа по файлу и информации"""
    if not file_path:
        return "unknown"
    
    # Определяем по расширению файла
    file_ext = file_path.lower().split('.')[-1] if '.' in file_path else ''
    
    if file_ext in ['mp4', 'webm', 'mkv', 'mov']:
        return "video"
    elif file_ext in ['jpg', 'jpeg', 'png', 'webp']:
        return "photo"
    
    # Определяем по информации yt-dlp
    if info:
        duration = info.get('duration', 0)
        if duration > 0:
            return "video"
        
        formats = info.get('formats', [])
        for fmt in formats:
            if fmt.get('vcodec') != 'none':
                return "video"
            if fmt.get('acodec') != 'none' and fmt.get('vcodec') == 'none':
                return "photo"
    
    return "unknown"

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

async def safe_send_video(client, chat_id, file_path, caption=""):
    """Безопасная отправка видео"""
    try:
        if not os.path.exists(file_path):
            raise Exception(f"Файл не существует: {file_path}")
            
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            raise Exception(f"Файл пустой: {file_path}")
            
        if file_size > 1900 * 1024 * 1024:
            raise Exception("Файл слишком большой для Telegram")
            
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
            
        if file_size > 10 * 1024 * 1024:
            raise Exception("Фото слишком большое для Telegram")
            
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
        "Привет! 👋\n\n"
        "📥 Отправь ссылку на:\n"
        "• Instagram (видео, фото, рилсы)\n"
        "• YouTube (видео, Shorts)\n\n"
        "⚡ Простое и быстрое скачивание!\n"
        "📹 Видео до 2GB | 📸 Фото до 10MB\n"
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
        "• Instagram видео/рилсы\n"
        "• Instagram фото\n"
        "• YouTube видео\n"
        "• YouTube Shorts\n\n"
        "⚡ Просто отправь ссылку - бот сам определит тип контента!\n"
        "📹 Максимальный размер видео: 2GB\n"
        "📸 Максимальный размер фото: 10MB"
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
        status = await message.reply_text("⏳ Обработка ссылки...")
        
        if "youtube" in url or "youtu.be" in url:
            # YouTube обработка
            tmp_dir = tempfile.mkdtemp()
            file_path = None
            
            try:
                await status.edit_text("🔍 Анализирую YouTube видео...")
                video_info = await asyncio.to_thread(get_youtube_info, url)
                
                if not video_info:
                    raise Exception("Не удалось получить информацию о видео")
                
                title = video_info.get('title', 'Неизвестное видео')
                duration = video_info.get('duration', 0)
                
                if duration > 3600:
                    raise Exception("Видео слишком длинное (больше 1 часа)")
                
                await status.edit_text(f"🎬 {title}\n📥 Скачиваю...")
                
                file_path = await asyncio.to_thread(download_youtube_video_best, url, tmp_dir)
                
                await status.edit_text("📤 Отправляю видео...")
                
                await safe_send_video(
                    client,
                    message.chat.id,
                    file_path,
                    caption=f"📥 {title}\n\nСкачано через @azams_bot"
                )
                logger.info("✅ YouTube видео успешно отправлено")

            except Exception as e:
                logger.error(f"❌ YouTube ошибка: {e}")
                raise Exception(f"Не удалось скачать YouTube видео: {str(e)}")
                
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
                
        elif "instagram.com" in url:
            # Instagram обработка - УПРОЩЕННАЯ
            if not os.path.exists("cookies.txt"):
                await status.edit_text("❌ Файл cookies.txt не найден.")
                await asyncio.sleep(5)
                await status.delete()
                return
                
            tmp_dir = tempfile.mkdtemp()
            file_path = None
            
            try:
                await status.edit_text("📥 Скачиваю Instagram контент...")
                
                # Пробуем оба метода
                try:
                    file_path, info = await asyncio.to_thread(download_instagram_simple, url, tmp_dir)
                except Exception as e:
                    logger.warning(f"Первый метод не сработал: {e}, пробую прямой метод...")
                    file_path, info = await asyncio.to_thread(download_instagram_direct, url, tmp_dir)
                
                if not file_path:
                    raise Exception("Не удалось скачать контент")
                
                # Определяем тип медиа
                media_type = get_instagram_media_type(file_path, info)
                title = info.get('title', 'Instagram контент') if info else 'Instagram контент'
                
                await status.edit_text("📤 Отправляю...")
                
                if media_type == "video":
                    await safe_send_video(
                        client,
                        message.chat.id,
                        file_path,
                        caption=f"📥 {title}\n\nСкачано через @azams_bot"
                    )
                    logger.info("✅ Instagram видео отправлено")
                    
                elif media_type == "photo":
                    await safe_send_photo(
                        client,
                        message.chat.id,
                        file_path,
                        caption=f"📸 {title}\n\nСкачано через @azams_bot"
                    )
                    logger.info("✅ Instagram фото отправлено")
                    
                else:
                    # Пробуем определить по расширению
                    if file_path.lower().endswith(('.mp4', '.webm', '.mkv')):
                        await safe_send_video(
                            client,
                            message.chat.id,
                            file_path,
                            caption=f"📥 {title}\n\nСкачано через @azams_bot"
                        )
                        logger.info("✅ Instagram видео отправлено (автоопределение)")
                    else:
                        await safe_send_photo(
                            client,
                            message.chat.id,
                            file_path,
                            caption=f"📸 {title}\n\nСкачано через @azams_bot"
                        )
                        logger.info("✅ Instagram фото отправлено (автоопределение)")

            except Exception as e:
                logger.error(f"❌ Instagram ошибка: {e}")
                raise Exception(f"Не удалось скачать Instagram контент. Убедитесь что:\n• Ссылка правильная\n• Контент доступен\n• Аккаунт не приватный")
                
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
                            file_path = os.path.join(tmp_dir, file)
                            if os.path.exists(file_path):
                                os.remove(file_path)
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
                    f"❌ {str(e)}\n\n"
                    "📥 Попробуйте:\n"
                    "• Другую ссылку\n"
                    "• Проверить доступность контента\n"
                    "• Убедиться что аккаунт не приватный"
                )
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
    
    # Проверка cookies
    if os.path.exists("cookies.txt"):
        logger.info("✅ Файл cookies.txt найден - Instagram доступен")
    else:
        logger.warning("⚠️ Файл cookies.txt не найден - Instagram недоступен")
    
    logger.info("🚀 Запуск бота с упрощенной Instagram загрузкой...")
    app.run()
