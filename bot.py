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

API_ID = 26670278
API_HASH = "e3d77390fd9c22d98bb6bddca86fef1a"
BOT_TOKEN = "6788128988:AAEMmCSafiiEqtS5UWQQxfo--W0On7B6Q08"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------------- ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ -------------------------
user_processing = {}
processed_messages = set()

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

# ------------------------- ОПТИМИЗИРОВАННЫЙ КЛИЕНТ -------------------------
app = SafeClient(
    "video_bot_new_session_2024",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    sleep_threshold=60,
    workers=150,
    max_concurrent_transmissions=10,
)

# ------------------------- ОПТИМИЗИРОВАННЫЙ Instagram Downloader -------------------------
class InstagramDownloader:
    def __init__(self):
        # СУПЕР-БЫСТРЫЕ НАСТРОЙКИ yt-dlp
        self.ultra_fast_ydl_opts = {
            'outtmpl': 'downloads/%(id)s.%(ext)s',
            'format': 'best[height<=720]',
            'cookiefile': 'cookies.txt',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'noplaylist': True,
            
            # ⚡⚡⚡ АГРЕССИВНЫЕ ОПТИМИЗАЦИИ ⚡⚡⚡
            'socket_timeout': 10,
            'extractretry': 0,
            'retries': 1,
            'fragment_retries': 1,
            'skip_unavailable_fragments': True,
            'keep_fragments': False,
            'concurrent_fragment_downloads': 8,
            'noprogress': True,
            
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15',
                'Accept': '*/*',
                'Accept-Encoding': 'gzip, deflate, br',
            }
        }
        
        # НАСТРОЙКИ ДЛЯ YOUTUBE SHORTS (БЕЗ ОШИБКИ АВТОРИЗАЦИИ)
        self.youtube_shorts_opts = {
            'outtmpl': 'downloads/%(id)s.%(ext)s',
            'format': 'best[height<=720]',
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 8,
            'retries': 1,
            'concurrent_fragment_downloads': 6,
            'noprogress': True,
            'no_check_certificate': True,
            'prefer_insecure': True,
            'geo_bypass': True,
        }
        
        self.thread_pool = ThreadPoolExecutor(max_workers=4)

    async def download_instagram_content(self, url: str, out_path: str):
        """УНИВЕРСАЛЬНАЯ функция для скачивания любого контента Instagram"""
        try:
            # Определяем тип контента по URL
            content_type = self._determine_content_type(url)
            logger.info(f"🔍 Определен тип контента: {content_type}")
            
            if '/stories/' in url:
                return await self._download_story(url, out_path, content_type)
            else:
                return await self._download_with_ytdlp(url, out_path, content_type)
        except Exception as e:
            logger.warning(f"yt-dlp не сработал: {e}, пробуем instaloader")
            return await self._download_with_instaloader(url, out_path)

    def _determine_content_type(self, url: str) -> str:
        """Определяет тип контента по URL"""
        if '/reel/' in url or '/reels/' in url or '/tv/' in url:
            return 'video'
        elif '/p/' in url:
            return 'post'
        elif '/stories/' in url:
            return 'story'
        else:
            return 'auto'

    async def _download_story(self, url: str, out_path: str, content_type: str):
        """Специальная функция для скачивания историй"""
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self.thread_pool, 
                self._download_story_fast, 
                url, out_path, content_type
            )
            return result
        except Exception as e:
            logger.warning(f"Быстрый метод stories не сработал: {e}, пробуем instaloader")
            return await self._download_story_with_instaloader(url, out_path, content_type)

    def _download_story_fast(self, url: str, out_path: str, content_type: str):
        """БЫСТРОЕ скачивание историй через yt-dlp"""
        ydl_opts = self.ultra_fast_ydl_opts.copy()
        ydl_opts['outtmpl'] = os.path.join(out_path, 'story_%(id)s.%(ext)s')
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            result = {
                'type': 'story',
                'files': [],
                'title': f"instagram_story_{info.get('id', 'unknown')}",
                'webpage_url': url
            }
            
            # БЫСТРЫЙ поиск файлов
            if info.get('requested_downloads'):
                for download in info['requested_downloads']:
                    file_path = download['filepath']
                    if os.path.exists(file_path) and self._is_media_file(file_path):
                        result['files'].append(file_path)
            
            # Быстрый поиск в директории
            if not result['files']:
                for file in os.listdir(out_path):
                    file_path = os.path.join(out_path, file)
                    if self._is_media_file(file_path):
                        result['files'].append(file_path)
            
            # Быстрое определение типа
            if result['files']:
                ext = result['files'][0].split('.')[-1].lower()
                if ext in ['mp4', 'mov', 'avi']:
                    result['type'] = 'story_video'
                else:
                    result['type'] = 'story_photo'
            
            return result

    async def _download_with_ytdlp(self, url: str, out_path: str, content_type: str):
        """Скачивание через yt-dlp для постов"""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self.thread_pool,
            self._download_with_ytdlp_fast,
            url, out_path, content_type
        )
        return result

    def _download_with_ytdlp_fast(self, url: str, out_path: str, content_type: str):
        """БЫСТРОЕ скачивание через yt-dlp"""
        ydl_opts = self.ultra_fast_ydl_opts.copy()
        ydl_opts['outtmpl'] = os.path.join(out_path, '%(id)s.%(ext)s')
        
        # Настраиваем формат в зависимости от типа контента
        if content_type == 'video':
            ydl_opts['format'] = 'best[ext=mp4]/best'
        elif content_type == 'photo':
            ydl_opts['format'] = 'best[ext=jpg]/best[ext=png]/best'
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            result = {
                'type': 'unknown',
                'files': [],
                'title': info.get('title', 'instagram_content'),
                'webpage_url': info.get('webpage_url', url)
            }
            
            # БЫСТРЫЙ сбор файлов
            if info.get('requested_downloads'):
                for download in info['requested_downloads']:
                    file_path = download['filepath']
                    if os.path.exists(file_path) and self._is_media_file(file_path):
                        result['files'].append(file_path)
            
            # Быстрый поиск в директории
            if not result['files']:
                for file in os.listdir(out_path):
                    file_path = os.path.join(out_path, file)
                    if self._is_media_file(file_path):
                        result['files'].append(file_path)
            
            # Быстрое определение типа контента
            if info.get('_type') == 'playlist' or len(result['files']) > 1:
                result['type'] = 'carousel'
            else:
                if result['files']:
                    ext = result['files'][0].split('.')[-1].lower()
                    if ext in ['jpg', 'png', 'jpeg']:
                        result['type'] = 'photo'
                    elif ext in ['mp4', 'mov', 'avi']:
                        result['type'] = 'video'
            
            return result

    # ВАШИ ОРИГИНАЛЬНЫЕ МЕТОДЫ (ОСТАВЛЯЕМ БЕЗ ИЗМЕНЕНИЙ)
    async def _download_story_with_instaloader(self, url: str, out_path: str, content_type: str):
        """Скачивание историй через instaloader"""
        try:
            L = instaloader.Instaloader(
                dirname_pattern=out_path,
                filename_pattern='{profile}_{date_utc}',
                download_pictures=(content_type != 'video'),
                download_videos=(content_type != 'photo'),
                download_geotags=False,
                download_comments=False,
                save_metadata=False,
                compress_json=False
            )
            
            # Извлекаем username из URL истории
            username = self._extract_story_username(url)
            if not username:
                raise Exception("Не удалось извлечь username из URL истории")
            
            # Скачиваем истории
            profile = instaloader.Profile.from_username(L.context, username)
            
            downloaded_files = []
            story_count = 0
            
            # Получаем все истории пользователя
            for story in L.get_stories([profile.userid]):
                for item in story.get_items():
                    if story_count >= 5:
                        break
                        
                    # Скачиваем каждый элемент истории
                    L.download_storyitem(item, target=os.path.join(out_path, f"story_{username}"))
                    
                    # Находим скачанные файлы и фильтруем по типу
                    for file in os.listdir(out_path):
                        if file.startswith(f"story_{username}") and not file.endswith('.txt'):
                            full_path = os.path.join(out_path, file)
                            if self._is_media_file(full_path):
                                # Фильтруем по типу контента
                                ext = full_path.split('.')[-1].lower()
                                if content_type == 'video' and ext in ['mp4', 'mov', 'avi']:
                                    downloaded_files.append(full_path)
                                elif content_type != 'video' and ext in ['jpg', 'png', 'jpeg']:
                                    downloaded_files.append(full_path)
                                elif content_type == 'auto':
                                    downloaded_files.append(full_path)
                    
                    story_count += 1
            
            if not downloaded_files:
                raise Exception("Не удалось скачать истории")
            
            result = {
                'type': 'story',
                'files': downloaded_files,
                'title': f"instagram_story_{username}",
                'webpage_url': url,
                'count': len(downloaded_files)
            }
            
            # Определяем тип файлов
            if downloaded_files:
                ext = downloaded_files[0].split('.')[-1].lower()
                if ext in ['jpg', 'png', 'jpeg']:
                    result['type'] = 'story_photo'
                elif ext in ['mp4', 'mov', 'avi']:
                    result['type'] = 'story_video'
            
            return result
            
        except Exception as e:
            raise Exception(f"Instaloader ошибка для историй: {str(e)}")

    async def _download_with_instaloader(self, url: str, out_path: str):
        """Резервный метод через instaloader для постов"""
        try:
            L = instaloader.Instaloader(
                dirname_pattern=out_path,
                filename_pattern='{shortcode}',
                download_pictures=True,
                download_videos=True,
                download_geotags=False,
                download_comments=False,
                save_metadata=False,
                compress_json=False
            )
            
            # Извлекаем shortcode из URL
            shortcode = self._extract_shortcode(url)
            if not shortcode:
                raise Exception("Не удалось извлечь shortcode из URL")
            
            # Скачиваем пост
            post = instaloader.Post.from_shortcode(L.context, shortcode)
            L.download_post(post, target=out_path)
            
            # Собираем скачанные файлы (только медиа)
            downloaded_files = []
            for file in os.listdir(out_path):
                file_path = os.path.join(out_path, file)
                if self._is_media_file(file_path):
                    downloaded_files.append(file_path)
            
            result = {
                'type': 'carousel' if post.mediacount > 1 else 'photo',
                'files': downloaded_files,
                'title': f"instagram_{shortcode}",
                'webpage_url': url
            }
            
            # Определяем тип по расширению первого файла
            if downloaded_files:
                ext = downloaded_files[0].split('.')[-1].lower()
                if ext in ['mp4', 'mov', 'avi']:
                    result['type'] = 'video'
                    
            return result
            
        except Exception as e:
            raise Exception(f"Instaloader ошибка: {str(e)}")

    def _is_media_file(self, file_path: str) -> bool:
        """Проверяет, является ли файл медиафайлом"""
        media_extensions = ['.jpg', '.jpeg', '.png', '.mp4', '.mov', '.avi', '.webm']
        file_ext = os.path.splitext(file_path)[1].lower()
        return file_ext in media_extensions and os.path.isfile(file_path)

    def _extract_story_username(self, url: str):
        """Извлекает username из URL истории"""
        patterns = [
            r'instagram\.com/stories/([^/?]+)',
            r'instagram\.com/stories/([^/?]+)/(\d+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def _extract_shortcode(self, url: str):
        """Извлекает shortcode из URL Instagram"""
        patterns = [
            r'instagram\.com/p/([^/?]+)',
            r'instagram\.com/reel/([^/?]+)',
            r'instagram\.com/stories/[^/]+/([^/?]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    # НОВАЯ ФУНКЦИЯ ДЛЯ YOUTUBE SHORTS
    async def download_youtube_shorts(self, url: str, out_path: str):
        """Скачивание YouTube Shorts"""
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self.thread_pool,
                self._download_youtube_shorts_fast,
                url, out_path
            )
            return result
        except Exception as e:
            logger.error(f"Ошибка скачивания YouTube Shorts: {e}")
            raise Exception(f"Не удалось скачать YouTube Shorts: {str(e)}")

    def _download_youtube_shorts_fast(self, url: str, out_path: str):
        """Быстрое скачивание YouTube Shorts"""
        ydl_opts = self.youtube_shorts_opts.copy()
        ydl_opts['outtmpl'] = os.path.join(out_path, 'shorts_%(id)s.%(ext)s')
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            # Поиск скачанного файла
            file_path = None
            if info.get('requested_downloads'):
                for download in info['requested_downloads']:
                    if os.path.exists(download['filepath']):
                        file_path = download['filepath']
                        break
            
            if not file_path:
                for file in os.listdir(out_path):
                    if file.startswith('shorts_') and file.endswith(('.mp4', '.webm')):
                        file_path = os.path.join(out_path, file)
                        break
            
            if not file_path:
                raise Exception("Не удалось найти скачанный файл Shorts")
            
            return {
                'type': 'video',
                'files': [file_path],
                'title': info.get('title', 'youtube_shorts'),
                'webpage_url': url
            }

# ------------------------- ОПТИМИЗИРОВАННЫЕ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ -------------------------
def extract_first_url(text: str) -> str:
    match = re.search(r"(https?://[^\s]+)", text)
    return match.group(1) if match else ""

def normalize_url(url: str) -> str:
    if "youtu.be/" in url:
        video_id = url.split("/")[-1].split("?")[0]
        return f"https://www.youtube.com/watch?v={video_id}"
    return url

def is_youtube_shorts(url: str) -> bool:
    """Проверяет, является ли ссылка YouTube Shorts"""
    return "youtube.com/shorts/" in url or ("youtu.be/" in url and len(url.split("/")[-1]) == 11)

def get_youtube_direct_url(url: str) -> str:
    ydl_opts = {
        "quiet": True, 
        "skip_download": True, 
        "format": "mp4[height<=720]/best[ext=mp4]/best",
        "socket_timeout": 8
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
        "socket_timeout": 10,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)

def check_cookies_file():
    if not os.path.exists("cookies.txt"):
        logger.error("❌ Файл cookies.txt не найден!")
        return False
    logger.info("✅ Файл cookies.txt найден")
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

# ------------------------- ОБНОВЛЕННЫЕ ОБРАБОТЧИКИ СООБЩЕНИЙ -------------------------

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
            "⚡ **ULTRA FAST Downloader** ⚡\n\n"
            "📥 Отправь ссылку на:\n"
            "• Instagram: фото, видео, рилсы, карусели, истории\n"
            "• YouTube: видео, Shorts\n\n"
            "🚀 Оптимизировано для максимальной скорости!"
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
        "• Instagram фото/видео/рилс/карусели/истории\n"
        "• YouTube видео/Shorts\n\n"
        "⚡ **ОПТИМИЗИРОВАНО ДЛЯ СКОРОСТИ!**\n"
        "📌 Бот автоматически определит тип контента"
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
    insta_downloader = InstagramDownloader()
    tmp_dir = None
    
    try:
        url = normalize_url(url)
        logger.info(f"🔄 Нормализованный URL: {url}")
        
        status = await message.reply_text("⚡ Определяю тип контента...")
        
        if is_youtube_shorts(url):
            # ОБРАБОТКА YOUTUBE SHORTS
            await _handle_youtube_shorts(client, message, url, status)
            
        elif "youtube" in url or "youtu.be" in url:
            # ОБЫЧНОЕ YOUTUBE ВИДЕО
            await _handle_youtube_fast(client, message, url, status)
            
        elif "instagram.com" in url:
            # INSTAGRAM КОНТЕНТ
            tmp_dir = tempfile.mkdtemp()
            await _handle_instagram_fast(client, message, url, status, insta_downloader, tmp_dir)

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

async def _handle_youtube_shorts(client, message, url, status):
    """Обработка YouTube Shorts"""
    try:
        await status.edit_text("⚡ Скачиваю YouTube Shorts...")
        tmp_dir = tempfile.mkdtemp()
        
        downloader = InstagramDownloader()
        content_info = await downloader.download_youtube_shorts(url, tmp_dir)
        
        if not content_info.get('files'):
            raise Exception("Не удалось скачать Shorts")
        
        await status.edit_text("📤 Отправляю Shorts...")
        
        file_path = content_info['files'][0]
        await message.reply_video(
            file_path,
            caption="🎬 YouTube Shorts через @azams_bot"
        )
        
        logger.info("✅ YouTube Shorts отправлен")
        
    except Exception as e:
        raise e
    finally:
        if tmp_dir:
            safe_remove_directory(tmp_dir)

async def _handle_youtube_fast(client, message, url, status):
    """ОПТИМИЗИРОВАННАЯ обработка YouTube"""
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

async def _handle_instagram_fast(client, message, url, status, downloader, tmp_dir):
    """ОПТИМИЗИРОВАННАЯ обработка Instagram"""
    if not check_cookies_file():
        await status.edit_text("❌ Файл cookies.txt не найден. Instagram недоступен.")
        await asyncio.sleep(3)
        return
        
    try:
        await status.edit_text("⚡ Скачиваю контент...")
        
        content_info = await downloader.download_instagram_content(url, tmp_dir)
        
        if not content_info.get('files'):
            raise Exception("Не удалось скачать файлы")
        
        # БЫСТРАЯ проверка расширений
        validated_files = []
        for file_path in content_info['files']:
            if os.path.exists(file_path):
                fixed_path = validate_and_fix_extension(file_path)
                validated_files.append(fixed_path)
        
        if not validated_files:
            raise Exception("Нет валидных файлов для отправки")
        
        content_info['files'] = validated_files
        
        await status.edit_text(f"📤 Отправляю {content_info['type']}...")
        
        # ОПТИМИЗИРОВАННАЯ отправка
        await send_content_fast(client, message, content_info)
        
        logger.info(f"✅ Instagram {content_info['type']} отправлен ({len(validated_files)} файлов)")
        
    except Exception as e:
        raise e

async def send_content_fast(client, message, content_info):
    """ОПТИМИЗИРОВАННАЯ отправка контента"""
    files = content_info['files']
    content_type = content_info['type']
    
    if content_type in ['photo', 'story_photo']:
        # ПАРАЛЛЕЛЬНАЯ отправка фото
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
        # ПАРАЛЛЕЛЬНАЯ отправка видео
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
        await _send_carousel_fast(client, message, files)

async def _send_carousel_fast(client, message, files):
    """ОПТИМИЗИРОВАННАЯ отправка карусели"""
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
            # Fallback - параллельная отправка по одному
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
    old_sessions = ["video_bot_new_session_2024.session", "video_bot_new_session_2024.session-journal"]
    for session_file in old_sessions:
        if os.path.exists(session_file):
            try:
                os.remove(session_file)
                logger.info(f"🗑️ Удален старый файл сессии: {session_file}")
            except Exception as e:
                logger.warning(f"Не удалось удалить {session_file}: {e}")
    
    if os.path.exists("cookies.txt"):
        logger.info("✅ Файл cookies.txt найден - Instagram доступен")
    else:
        logger.warning("⚠️ Файл cookies.txt не найден - Instagram недоступен")
    
    if not os.path.exists("downloads"):
        os.makedirs("downloads")
    
    logger.info("🚀 ЗАПУСК ПОЛНОГО ОПТИМИЗИРОВАННОГО БОТА...")
    logger.info("📸 Поддержка: Instagram + YouTube Shorts")
    
    try:
        app.run()
        logger.info("✅ Бот успешно запущен и готов к работе!")
    except Exception as e:
        logger.error(f"❌ Ошибка запуска бота: {e}")
