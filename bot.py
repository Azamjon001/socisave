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

# ------------------------- INSTAGRAM ФУНКЦИИ -------------------------

def check_cookies_file():
    if not os.path.exists("cookies.txt"):
        logger.error("❌ Файл cookies.txt не найден!")
        return False
    logger.info("✅ Файл cookies.txt найден")
    return True

def get_instagram_media_info(url: str):
    """Получаем информацию о медиа Instagram"""
    if not check_cookies_file():
        raise FileNotFoundError("Файл cookies.txt не найден.")
    
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "cookiefile": "cookies.txt",
        "ignoreerrors": True,
        "extract_flat": False,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info
    except Exception as e:
        logger.error(f"Ошибка получения информации Instagram: {e}")
        raise

def download_instagram_single_media(url: str, out_path: str):
    """Скачиваем одиночное медиа Instagram (фото или видео)"""
    if not check_cookies_file():
        raise FileNotFoundError("Файл cookies.txt не найден.")
    
    ydl_opts = {
        "outtmpl": os.path.join(out_path, "%(title).100s.%(ext)s"),
        "cookiefile": "cookies.txt",
        "quiet": False,
        "ignoreerrors": True,
        "retries": 3,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            if not os.path.exists(filename):
                raise Exception(f"Файл не создан: {filename}")
                
            file_size = os.path.getsize(filename)
            if file_size == 0:
                os.remove(filename)
                raise Exception(f"Файл пустой: {filename}")
                
            logger.info(f"✅ Instagram медиа скачано: {filename} ({file_size} bytes)")
            return filename, info
            
    except Exception as e:
        logger.error(f"Ошибка скачивания Instagram: {e}")
        raise

def download_instagram_carousel(url: str, out_path: str):
    """Скачиваем карусель Instagram (несколько фото)"""
    if not check_cookies_file():
        raise FileNotFoundError("Файл cookies.txt не найден.")
    
    ydl_opts = {
        "outtmpl": os.path.join(out_path, "%(playlist_index)s_%(title).100s.%(ext)s"),
        "cookiefile": "cookies.txt",
        "quiet": False,
        "ignoreerrors": True,
        "retries": 3,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Скачиваем все элементы карусели
            result = ydl.extract_info(url, download=True)
            
            # Получаем список скачанных файлов
            downloaded_files = []
            if '_type' in result and result['_type'] == 'playlist':
                for entry in result['entries']:
                    if entry and '_filename' in entry:
                        filename = entry['_filename']
                        if os.path.exists(filename):
                            downloaded_files.append(filename)
                            logger.info(f"✅ Скачан файл карусели: {filename}")
            
            if not downloaded_files:
                raise Exception("Не удалось скачать файлы карусели")
                
            return downloaded_files, result
            
    except Exception as e:
        logger.error(f"Ошибка скачивания Instagram карусели: {e}")
        raise

def is_instagram_video(info):
    """Проверяем является ли контент видео"""
    if not info:
        return False
    
    # Проверяем расширение файла
    filename = info.get('_filename', '')
    if filename and any(filename.endswith(ext) for ext in ['.mp4', '.webm', '.mkv']):
        return True
    
    # Проверяем длительность
    if info.get('duration'):
        return True
    
    # Проверяем форматы
    formats = info.get('formats', [])
    for fmt in formats:
        if fmt.get('vcodec') != 'none':
            return True
    
    return False

def is_instagram_photo(info):
    """Проверяем является ли контент фото"""
    if not info:
        return False
    
    # Проверяем расширение файла
    filename = info.get('_filename', '')
    if filename and any(filename.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp']):
        return True
    
    # Если это карусель (несколько фото)
    if info.get('_type') == 'playlist':
        return True
    
    return False

def is_instagram_carousel(info):
    """Проверяем является ли контент каруселью (несколько фото)"""
    if not info:
        return False
    
    # Проверяем тип плейлиста
    if info.get('_type') == 'playlist':
        entries = info.get('entries', [])
        if len(entries) > 1:
            return True
    
    return False

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

async def safe_send_media_group(client, chat_id, media_list):
    """Безопасная отправка группы медиа (для карусели)"""
    try:
        if len(media_list) > 10:
            media_list = media_list[:10]  # Ограничение Telegram
        
        return await client.send_media_group(
            chat_id=chat_id,
            media=media_list
        )
    except Exception as e:
        logger.error(f"❌ Ошибка отправки группы медиа: {e}")
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
        "• Instagram (видео, фото, карусели, рилсы)\n"
        "• YouTube (видео, Shorts)\n\n"
        "⚡ Автоматически определяем тип контента!\n"
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
        "• Instagram одиночные фото\n"
        "• Instagram карусели (несколько фото)\n"
        "• YouTube видео\n"
        "• YouTube Shorts\n\n"
        "⚡ Автоматическое определение типа контента!\n"
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
            # Instagram обработка
            if not os.path.exists("cookies.txt"):
                await status.edit_text("❌ Файл cookies.txt не найден.")
                await asyncio.sleep(5)
                await status.delete()
                return
                
            tmp_dir = tempfile.mkdtemp()
            
            try:
                await status.edit_text("🔍 Анализирую Instagram контент...")
                
                # Получаем информацию о медиа
                media_info = await asyncio.to_thread(get_instagram_media_info, url)
                
                if not media_info:
                    raise Exception("Не удалось получить информацию о контенте")
                
                title = media_info.get('title', 'Instagram контент')
                
                # Определяем тип контента и обрабатываем соответственно
                if is_instagram_carousel(media_info):
                    # Карусель с несколькими фото
                    await status.edit_text(f"🖼️ {title}\n📥 Скачиваю карусель ({len(media_info.get('entries', []))} фото)...")
                    
                    downloaded_files, info = await asyncio.to_thread(download_instagram_carousel, url, tmp_dir)
                    
                    if not downloaded_files:
                        raise Exception("Не удалось скачать фото карусели")
                    
                    await status.edit_text("📤 Отправляю карусель...")
                    
                    # Создаем медиа группу для отправки нескольких фото
                    media_group = []
                    for i, file_path in enumerate(downloaded_files):
                        if i == 0:
                            # Первое фото с подписью
                            media_group.append(InputMediaPhoto(
                                media=file_path,
                                caption=f"🖼️ {title}\n\nСкачано через @azams_bot"
                            ))
                        else:
                            # Остальные фото без подписи
                            media_group.append(InputMediaPhoto(media=file_path))
                    
                    await safe_send_media_group(client, message.chat.id, media_group)
                    logger.info(f"✅ Instagram карусель отправлена ({len(downloaded_files)} фото)")
                    
                elif is_instagram_video(media_info):
                    # Видео
                    await status.edit_text(f"🎬 {title}\n📥 Скачиваю видео...")
                    file_path, info = await asyncio.to_thread(download_instagram_single_media, url, tmp_dir)
                    
                    await status.edit_text("📤 Отправляю видео...")
                    await safe_send_video(
                        client,
                        message.chat.id,
                        file_path,
                        caption=f"📥 {title}\n\nСкачано через @azams_bot"
                    )
                    logger.info("✅ Instagram видео отправлено")
                    
                elif is_instagram_photo(media_info):
                    # Одиночное фото
                    await status.edit_text(f"📸 {title}\n📥 Скачиваю фото...")
                    file_path, info = await asyncio.to_thread(download_instagram_single_media, url, tmp_dir)
                    
                    await status.edit_text("📤 Отправляю фото...")
                    await safe_send_photo(
                        client,
                        message.chat.id,
                        file_path,
                        caption=f"📸 {title}\n\nСкачано через @azams_bot"
                    )
                    logger.info("✅ Instagram фото отправлено")
                    
                else:
                    # Пробуем скачать как одиночное медиа
                    await status.edit_text(f"📁 {title}\n📥 Скачиваю контент...")
                    file_path, info = await asyncio.to_thread(download_instagram_single_media, url, tmp_dir)
                    
                    # Определяем тип по расширению
                    if file_path.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                        await status.edit_text("📤 Отправляю фото...")
                        await safe_send_photo(
                            client,
                            message.chat.id,
                            file_path,
                            caption=f"📸 {title}\n\nСкачано через @azams_bot"
                        )
                        logger.info("✅ Instagram фото отправлено (автоопределение)")
                    else:
                        await status.edit_text("📤 Отправляю видео...")
                        await safe_send_video(
                            client,
                            message.chat.id,
                            file_path,
                            caption=f"📥 {title}\n\nСкачано через @azams_bot"
                        )
                        logger.info("✅ Instagram видео отправлено (автоопределение)")

            except Exception as e:
                logger.error(f"❌ Instagram ошибка: {e}")
                raise Exception(f"Не удалось скачать Instagram контент: {str(e)}")
                
            finally:
                # Очистка для Instagram
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
                    "• Более короткое видео"
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
    
    logger.info("🚀 Запуск бота с поддержкой Instagram каруселей...")
    app.run()
