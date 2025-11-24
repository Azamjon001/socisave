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
from pyrogram.types import InputMediaPhoto, InputMediaVideo
import instaloader
import aiohttp
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import hashlib

API_ID = 26670278
API_HASH = "e3d77390fd9c22d98bb6bddca86fef1a"
BOT_TOKEN = "6788128988:AAEMmCSafiiEqtS5UWQQxfo--W0On7B6Q08"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------------- ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ -------------------------
user_processing = {}
processed_messages = set()

# ------------------------- ОПТИМИЗИРОВАННЫЙ SafeClient -------------------------
class SafeClient(Client):
    async def send(self, *args, **kwargs):
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

# ------------------------- ОПТИМИЗИРОВАННЫЙ КЛИЕНТ -------------------------
app = SafeClient(
    "video_bot_new_session_2024",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    sleep_threshold=30,
    workers=100,
)

# ------------------------- УПРОЩЕННЫЙ Instagram Downloader -------------------------
class InstagramDownloader:
    def __init__(self):
        self.thread_pool = ThreadPoolExecutor(max_workers=3)
        self.request_counter = 0

    def get_ydl_opts(self, out_path: str):
        """ПРОСТЫЕ настройки yt-dlp - используем ТОЛЬКО cookies.txt"""
        return {
            'outtmpl': os.path.join(out_path, '%(id)s.%(ext)s'),
            'format': 'best[height<=720]',
            'cookiefile': 'cookies.txt',  # 🎯 ИСПОЛЬЗУЕМ ТОЛЬКО COOKIES.TXT
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'noplaylist': True,
            
            # ⚡ ОПТИМИЗАЦИИ СКОРОСТИ
            'socket_timeout': 15,
            'extractretry': 1,
            'retries': 2,
            'fragment_retries': 2,
            'skip_unavailable_fragments': True,
            'keep_fragments': False,
            'concurrent_fragment_downloads': 6,
            
            # 🎯 ПРОСТЫЕ ЗАГОЛОВКИ - НЕТ ЭМУЛЯЦИИ УСТРОЙСТВ
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Linux; Android 10; SM-G981B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Mobile Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Cache-Control': 'max-age=0',
            },
            'referer': 'https://www.instagram.com/',
            'origin': 'https://www.instagram.com',
        }

    async def download_instagram_content(self, url: str, out_path: str):
        """УПРОЩЕННАЯ функция для скачивания через cookies.txt"""
        try:
            self.request_counter += 1
            request_id = f"{int(time.time())}_{self.request_counter}"
            
            logger.info(f"📱 Запрос {request_id} через cookies.txt")
            
            loop = asyncio.get_event_loop()
            content_type = self._determine_content_type(url)
            logger.info(f"🔍 Определен тип контента: {content_type}")
            
            # 🎯 ВСЕ ЗАПРОСЫ ИДУТ ЧЕРЕЗ yt-dlp С COOKIES.TXT
            result = await loop.run_in_executor(
                self.thread_pool,
                self._download_with_ytdlp_simple,
                url, out_path, content_type
            )
            return result
            
        except Exception as e:
            logger.error(f"❌ Ошибка скачивания через cookies.txt: {e}")
            raise Exception(f"Не удалось скачать контент через Instagram аккаунт: {str(e)}")

    def _determine_content_type(self, url: str) -> str:
        """Определение типа контента"""
        if '/reel/' in url or '/reels/' in url or '/tv/' in url:
            return 'video'
        elif '/p/' in url:
            return 'post'
        elif '/stories/' in url:
            return 'story'
        else:
            return 'auto'

    def _download_with_ytdlp_simple(self, url: str, out_path: str, content_type: str):
        """ПРОСТОЙ метод скачивания через yt-dlp с cookies.txt"""
        ydl_opts = self.get_ydl_opts(out_path)
        
        # Настройка формата
        if content_type == 'video':
            ydl_opts['format'] = 'best[ext=mp4]/best'
        elif content_type == 'photo':
            ydl_opts['format'] = 'best[ext=jpg]/best[ext=png]/best'
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                result = {
                    'type': 'unknown',
                    'files': [],
                    'title': info.get('title', 'instagram_content'),
                    'webpage_url': info.get('webpage_url', url),
                }
                
                # Поиск скачанных файлов
                if info.get('requested_downloads'):
                    for download in info['requested_downloads']:
                        file_path = download['filepath']
                        if os.path.exists(file_path) and self._is_media_file_fast(file_path):
                            result['files'].append(file_path)
                
                # Поиск в директории
                if not result['files']:
                    for file in os.listdir(out_path):
                        file_path = os.path.join(out_path, file)
                        if self._is_media_file_fast(file_path):
                            result['files'].append(file_path)
                
                # Определение типа контента
                if info.get('_type') == 'playlist' or len(result['files']) > 1:
                    result['type'] = 'carousel'
                else:
                    if result['files']:
                        ext = result['files'][0].split('.')[-1].lower()
                        if ext in ['jpg', 'png', 'jpeg']:
                            result['type'] = 'photo'
                        elif ext in ['mp4', 'mov', 'avi']:
                            result['type'] = 'video'
                        elif 'story' in url.lower():
                            if ext in ['mp4', 'mov', 'avi']:
                                result['type'] = 'story_video'
                            else:
                                result['type'] = 'story_photo'
                
                logger.info(f"✅ Скачано {len(result['files'])} файлов типа {result['type']}")
                return result
                
        except Exception as e:
            logger.error(f"❌ Ошибка yt-dlp: {e}")
            raise

    def _is_media_file_fast(self, file_path: str) -> bool:
        """Быстрая проверка медиафайла"""
        media_extensions = {'.jpg', '.jpeg', '.png', '.mp4', '.mov', '.avi', '.webm'}
        file_ext = os.path.splitext(file_path)[1].lower()
        return file_ext in media_extensions and os.path.isfile(file_path)

# ------------------------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ -------------------------
def extract_first_url(text: str) -> str:
    match = re.search(r"(https?://[^\s]+)", text)
    return match.group(1) if match else ""

def normalize_url(url: str) -> str:
    if "youtu.be/" in url:
        video_id = url.split("/")[-1].split("?")[0]
        return f"https://www.youtube.com/watch?v={video_id}"
    return url

def get_youtube_direct_url(url: str) -> str:
    ydl_opts = {
        "quiet": True, 
        "skip_download": True, 
        "format": "mp4[height<=720]/best[ext=mp4]/best",
        "socket_timeout": 10
    }
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
        "socket_timeout": 15,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)

def check_cookies_file():
    if not os.path.exists("cookies.txt"):
        logger.error("❌ Файл cookies.txt не найден!")
        return False
    
    # Проверяем, что файл не пустой
    file_size = os.path.getsize("cookies.txt")
    if file_size == 0:
        logger.error("❌ Файл cookies.txt пустой!")
        return False
        
    logger.info(f"✅ Файл cookies.txt найден ({file_size} байт)")
    return True

async def cleanup_user_message(message, delay: int = 2):
    try:
        await asyncio.sleep(delay)
        await message.delete()
        logger.info(f"🗑️ Удалено сообщение пользователя {message.from_user.id}")
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение: {e}")

def cleanup_old_processed_messages():
    global processed_messages
    if len(processed_messages) > 1000:
        processed_messages = set(list(processed_messages)[-500:])
        logger.info("🧹 Очищены старые записи из processed_messages")

def safe_remove_directory(dir_path: str):
    try:
        if os.path.exists(dir_path):
            shutil.rmtree(dir_path)
            logger.info(f"✅ Удалена директория: {dir_path}")
    except Exception as e:
        logger.warning(f"⚠️ Не удалось удалить директорию {dir_path}: {e}")

def validate_and_fix_extension(file_path: str) -> str:
    if not os.path.exists(file_path):
        return file_path
    
    try:
        import filetype
        kind = filetype.guess(file_path)
        
        if kind is None:
            return file_path
        
        current_ext = os.path.splitext(file_path)[1].lower()
        correct_ext = f".{kind.extension}"
        
        if current_ext != correct_ext:
            new_file_path = os.path.splitext(file_path)[0] + correct_ext
            try:
                os.rename(file_path, new_file_path)
                logger.info(f"✅ Исправлено расширение: {current_ext} -> {correct_ext}")
                return new_file_path
            except Exception as e:
                logger.warning(f"⚠️ Не удалось исправить расширение: {e}")
    except ImportError:
        logger.warning("⚠️ Библиотека filetype не установлена, пропускаем проверку расширений")
    
    return file_path

# ------------------------- КОМАНДА ДЛЯ ПРОВЕРКИ COOKIES -------------------------
@app.on_message(filters.command("check_cookies"))
async def check_cookies_command(client, message):
    """Проверяет статус cookies.txt"""
    try:
        if check_cookies_file():
            file_size = os.path.getsize("cookies.txt")
            await message.reply_text(f"✅ cookies.txt активен\n📊 Размер: {file_size} байт\n\nАккаунт Instagram готов к работе!")
        else:
            await message.reply_text("❌ cookies.txt не найден или пустой!\n\nДобавьте файл cookies.txt для работы с Instagram")
    except Exception as e:
        await message.reply_text(f"❌ Ошибка проверки: {e}")

# ------------------------- ОБРАБОТЧИКИ СООБЩЕНИЙ -------------------------
@app.on_message(filters.command("start"))
async def start(client, message):
    logger.info(f"📩 Получена команда /start от {message.from_user.id}")
    
    message_id = f"start_{message.id}_{message.from_user.id}"
    
    if message_id in processed_messages:
        logger.info("🔄 Пропускаем дублирующее сообщение /start")
        return
        
    processed_messages.add(message_id)
    
    try:
        welcome_msg = await message.reply_text(
            "⚡ **Instagram Downloader** ⚡\n\n"
            "📥 Отправь ссылку на Instagram — я скачаю через твой аккаунт:\n"
            "• 📹 Видео и рилсы\n" 
            "• 📸 Фото\n"
            "• 🖼️ Карусели\n"
            "• 📱 Истории\n\n"
            "🔐 Используется аккаунт из cookies.txt\n"
            "📊 Проверить статус: /check_cookies"
        )
        logger.info(f"✅ Отправлено приветственное сообщение пользователю {message.from_user.id}")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки приветствия: {e}")
    
    cleanup_old_processed_messages()

@app.on_message(filters.command(["help", "info"]))
async def help_command(client, message):
    logger.info(f"📩 Получена команда help от {message.from_user.id}")
    
    message_id = f"help_{message.id}_{message.from_user.id}"
    
    if message_id in processed_messages:
        return
        
    processed_messages.add(message_id)
    
    help_text = (
        "🤖 **Помощь по боту**\n\n"
        "📥 Просто отправь ссылку на:\n"
        "• Instagram фото/видео/рилс\n"
        "• Instagram карусель\n" 
        "• Instagram историю\n\n"
        "🔐 **Используется твой аккаунт Instagram**\n"
        "📊 Проверить статус: /check_cookies\n\n"
        "⚡ Автоматическое определение типа контента"
    )
    
    try:
        await message.reply_text(help_text)
        logger.info(f"✅ Отправлена помощь пользователю {message.from_user.id}")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки помощи: {e}")
    
    cleanup_old_processed_messages()

@app.on_message(filters.text & filters.private)
async def handle_text(client, message):
    logger.info(f"📩 Получено сообщение от {message.from_user.id}: {message.text[:50]}...")
    
    message_id = f"text_{message.id}_{message.from_user.id}"
    
    if message_id in processed_messages:
        logger.info("🔄 Пропускаем дублирующее сообщение")
        return
        
    if message.text and message.text.startswith('/'):
        logger.info("⚙️ Пропускаем команду")
        return
    
    user_id = message.from_user.id
    text = message.text.strip()
    
    url = extract_first_url(text)
    logger.info(f"🔍 Извлечен URL: {url}")
    
    if not url or not any(d in url for d in ["youtube.com", "youtu.be", "instagram.com"]):
        logger.info("❌ URL не найден или не поддерживается")
        return

    processed_messages.add(message_id)
    
    if user_id in user_processing and user_processing[user_id].get('processing'):
        logger.info(f"⏳ Пользователь {user_id} уже имеет активный запрос")
        try:
            temp_msg = await message.reply_text("⚡ Уже обрабатываю предыдущий запрос...")
            await asyncio.sleep(2)
            await temp_msg.delete()
        except Exception as e:
            logger.error(f"❌ Ошибка уведомления о занятости: {e}")
        processed_messages.discard(message_id)
        return

    user_processing[user_id] = {'processing': True}
    
    status = None
    insta_downloader = InstagramDownloader()  # 🆕 Упрощенный загрузчик
    tmp_dir = None
    
    try:
        url = normalize_url(url)
        logger.info(f"🔄 Нормализованный URL: {url}")
        
        status = await message.reply_text("⚡ Определяю тип контента...")
        
        if "youtube" in url or "youtu.be" in url:
            await _handle_youtube_fast(client, message, url, status)
            
        elif "instagram.com" in url:
            tmp_dir = tempfile.mkdtemp()
            await _handle_instagram_simple(client, message, url, status, insta_downloader, tmp_dir)

        await message.delete()
        logger.info(f"✅ Обработка завершена для пользователя {user_id}")

    except Exception as e:
        logger.error(f"❌ Ошибка обработки для пользователя {user_id}: {e}")
        
        if status:
            try:
                error_msg = await message.reply_text(f"❌ Ошибка: {str(e)}")
                await asyncio.sleep(4)
                await error_msg.delete()
            except:
                pass
                
    finally:
        if status:
            try:
                await status.delete()
            except:
                pass
                
        if tmp_dir and os.path.exists(tmp_dir):
            safe_remove_directory(tmp_dir)
                
        if user_id in user_processing:
            user_processing[user_id]['processing'] = False
            
        cleanup_old_processed_messages()

async def _handle_youtube_fast(client, message, url, status):
    """Обработка YouTube"""
    try:
        await status.edit_text("🔗 Получаю прямую ссылку YouTube...")
        direct_url = await asyncio.to_thread(get_youtube_direct_url, url)
        
        await status.edit_text("📤 Отправляю видео...")
        await message.reply_video(
            direct_url, 
            caption="📥 YouTube видео через @azams_bot"
        )
        logger.info("✅ YouTube видео отправлено через прямую ссылку")
        
    except Exception as e:
        logger.warning(f"❌ Прямая ссылка не сработала: {e}, скачиваю файл...")
        await status.edit_text("📥 Скачиваю видео...")
        tmp_dir = tempfile.mkdtemp()
        
        try:
            file_path = await asyncio.to_thread(download_youtube_video, url, tmp_dir)
            await status.edit_text("📤 Отправляю видео...")
            await message.reply_video(
                file_path, 
                caption="📥 YouTube видео через @azams_bot"
            )
            logger.info("✅ YouTube видео отправлено как файл")
            
        except Exception as download_error:
            raise download_error
        finally:
            if os.path.exists(tmp_dir):
                safe_remove_directory(tmp_dir)

async def _handle_instagram_simple(client, message, url, status, downloader, tmp_dir):
    """УПРОЩЕННАЯ обработка Instagram через cookies.txt"""
    if not check_cookies_file():
        await status.edit_text("❌ Файл cookies.txt не найден. Instagram недоступен.\n\nИспользуй /check_cookies для проверки")
        await asyncio.sleep(5)
        return
        
    try:
        await status.edit_text("⚡ Скачиваю через Instagram аккаунт...")
        
        content_info = await downloader.download_instagram_content(url, tmp_dir)
        
        if not content_info.get('files'):
            raise Exception("Не удалось скачать файлы через Instagram аккаунт")
        
        # Проверка расширений
        validated_files = []
        for file_path in content_info['files']:
            if os.path.exists(file_path):
                fixed_path = validate_and_fix_extension(file_path)
                validated_files.append(fixed_path)
        
        if not validated_files:
            raise Exception("Нет валидных файлов для отправки")
        
        content_info['files'] = validated_files
        
        await status.edit_text(f"📤 Отправляю {content_info['type']}...")
        
        # Отправка контента
        await send_content_simple(client, message, content_info)
        
        logger.info(f"✅ Instagram {content_info['type']} отправлен ({len(validated_files)} файлов)")
        
    except Exception as e:
        raise e

async def send_content_simple(client, message, content_info):
    """УПРОЩЕННАЯ отправка контента"""
    files = content_info['files']
    content_type = content_info['type']
    
    if content_type in ['photo', 'story_photo']:
        tasks = []
        for file_path in files[:10]:
            if os.path.exists(file_path):
                task = message.reply_photo(
                    file_path,
                    caption=f"📸 Instagram {'история' if 'story' in content_type else 'фото'} через @azams_bot"
                )
                tasks.append(task)
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            
    elif content_type in ['video', 'story_video']:
        tasks = []
        for file_path in files[:10]:
            if os.path.exists(file_path):
                task = message.reply_video(
                    file_path,
                    caption=f"📹 Instagram {'история' if 'story' in content_type else 'видео'} через @azams_bot"
                )
                tasks.append(task)
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            
    elif content_type == 'carousel':
        await _send_carousel_simple(client, message, files)

async def _send_carousel_simple(client, message, files):
    """УПРОЩЕННАЯ отправка карусели"""
    media_group = []
    
    for i, file_path in enumerate(files[:10]):
        if not os.path.exists(file_path):
            continue
            
        try:
            if file_path.lower().endswith(('.jpg', '.jpeg', '.png')):
                media_item = InputMediaPhoto(file_path)
                if i == 0:
                    media_item.caption = "🖼️ Instagram карусель через @azams_bot"
                media_group.append(media_item)
                
            elif file_path.lower().endswith(('.mp4', '.mov', '.avi')):
                media_item = InputMediaVideo(file_path)
                if i == 0:
                    media_item.caption = "🎬 Instagram карусель через @azams_bot"
                media_group.append(media_item)
                
        except Exception as e:
            logger.warning(f"⚠️ Не удалось добавить файл: {file_path}, ошибка: {e}")
    
    if media_group:
        try:
            await message.reply_media_group(media_group)
            logger.info(f"✅ Медиагруппа отправлена ({len(media_group)} файлов)")
        except Exception as e:
            logger.error(f"❌ Ошибка отправки медиагруппы: {e}")
            # Отправка по одному
            tasks = []
            for file_path in files[:5]:
                if os.path.exists(file_path):
                    if file_path.lower().endswith(('.jpg', '.jpeg', '.png')):
                        tasks.append(message.reply_photo(file_path))
                    elif file_path.lower().endswith(('.mp4', '.mov', '.avi')):
                        tasks.append(message.reply_video(file_path))
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

# ------------------------- ЗАПУСК -------------------------
if __name__ == "__main__":
    # Очистка старых сессий
    old_sessions = ["video_bot_new_session_2024.session", "video_bot_new_session_2024.session-journal"]
    for session_file in old_sessions:
        if os.path.exists(session_file):
            try:
                os.remove(session_file)
                logger.info(f"🗑️ Удален старый файл сессии: {session_file}")
            except Exception as e:
                logger.warning(f"Не удалось удалить {session_file}: {e}")
    
    # Проверка cookies.txt
    if os.path.exists("cookies.txt"):
        file_size = os.path.getsize("cookies.txt")
        logger.info(f"✅ Файл cookies.txt найден ({file_size} байт) - Instagram доступен")
    else:
        logger.warning("⚠️ Файл cookies.txt не найден - Instagram недоступен")
    
    # Создание папки downloads
    if not os.path.exists("downloads"):
        os.makedirs("downloads")
    
    logger.info("🚀 ЗАПУСК УПРОЩЕННОГО БОТА...")
    logger.info("🎯 Используется ТОЛЬКО cookies.txt для Instagram")
    logger.info("⚡ Все запросы идут через один аккаунт Instagram")
    
    try:
        app.run()
        logger.info("✅ Бот успешно запущен и готов к работе!")
    except Exception as e:
        logger.error(f"❌ Ошибка запуска бота: {e}")
