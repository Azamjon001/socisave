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

# ------------------------- УЛУЧШЕННЫЙ Instagram Downloader -------------------------
class InstagramDownloader:
    def __init__(self):
        # ОПТИМИЗИРОВАННЫЕ НАСТРОЙКИ ДЛЯ ВСЕХ ТИПОВ КОНТЕНТА
        self.ultra_fast_ydl_opts = {
            'outtmpl': 'downloads/%(id)s.%(ext)s',
            'format': 'best[height<=720]',
            'cookiefile': 'cookies.txt',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'noplaylist': True,
            
            # ⚡ АГРЕССИВНЫЕ ОПТИМИЗАЦИИ ⚡
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
        
        # ОТДЕЛЬНЫЕ НАСТРОЙКИ ДЛЯ YOUTUBE SHORTS
        self.youtube_shorts_opts = {
            'outtmpl': 'downloads/%(id)s.%(ext)s',
            'format': 'best[height<=720][ext=mp4]/best[ext=mp4]',
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 8,
            'retries': 1,
            'concurrent_fragment_downloads': 6,
            'noprogress': True,
        }
        
        self.thread_pool = ThreadPoolExecutor(max_workers=4)

    async def download_instagram_content(self, url: str, out_path: str):
        """УНИВЕРСАЛЬНАЯ функция для скачивания Instagram контента"""
        try:
            loop = asyncio.get_event_loop()
            content_type = self._determine_content_type(url)
            logger.info(f"🔍 Определен тип контента: {content_type}")
            
            if '/stories/' in url:
                result = await loop.run_in_executor(
                    self.thread_pool, 
                    self._download_stories_ultra_fast, 
                    url, out_path
                )
            else:
                result = await loop.run_in_executor(
                    self.thread_pool,
                    self._download_instagram_ultra_fast,
                    url, out_path, content_type
                )
            return result
        except Exception as e:
            logger.warning(f"Быстрый метод не сработал: {e}")
            return await self._download_with_instaloader(url, out_path)

    async def download_youtube_shorts(self, url: str, out_path: str):
        """СПЕЦИАЛЬНАЯ функция для быстрого скачивания YouTube Shorts"""
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
            raise

    def _download_youtube_shorts_fast(self, url: str, out_path: str):
        """БЫСТРОЕ скачивание YouTube Shorts"""
        ydl_opts = self.youtube_shorts_opts.copy()
        ydl_opts['outtmpl'] = os.path.join(out_path, 'shorts_%(id)s.%(ext)s')
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            # БЫСТРЫЙ ПОИСК ФАЙЛА
            file_path = None
            if info.get('requested_downloads'):
                for download in info['requested_downloads']:
                    if os.path.exists(download['filepath']):
                        file_path = download['filepath']
                        break
            
            if not file_path:
                for file in os.listdir(out_path):
                    if file.startswith('shorts_') and file.endswith('.mp4'):
                        file_path = os.path.join(out_path, file)
                        break
            
            if not file_path:
                raise Exception("Не удалось найти скачанный файл Shorts")
            
            return {
                'type': 'video',
                'files': [file_path],
                'title': info.get('title', 'youtube_shorts'),
                'webpage_url': url,
                'duration': info.get('duration', 0)
            }

    def _download_stories_ultra_fast(self, url: str, out_path: str):
        """УЛЬТРА-БЫСТРОЕ скачивание Instagram Stories"""
        try:
            ydl_opts = self.ultra_fast_ydl_opts.copy()
            ydl_opts['outtmpl'] = os.path.join(out_path, 'story_%(id)s.%(ext)s')
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                files = []
                # БЫСТРЫЙ ПОИСК ФАЙЛОВ
                if info.get('requested_downloads'):
                    for download in info['requested_downloads']:
                        file_path = download['filepath']
                        if os.path.exists(file_path) and self._is_media_file_fast(file_path):
                            files.append(file_path)
                
                if not files:
                    for file in os.listdir(out_path):
                        file_path = os.path.join(out_path, file)
                        if self._is_media_file_fast(file_path):
                            files.append(file_path)
                
                # ОПРЕДЕЛЯЕМ ТИП STORIES (ВИДЕО ИЛИ ФОТО)
                content_type = 'story'
                if files:
                    first_file = files[0].lower()
                    if any(first_file.endswith(ext) for ext in ['.mp4', '.mov', '.avi']):
                        content_type = 'story_video'
                    else:
                        content_type = 'story_photo'
                
                return {
                    'type': content_type,
                    'files': files,
                    'title': f"instagram_story_{info.get('id', 'unknown')}",
                    'webpage_url': url,
                    'count': len(files)
                }
                
        except Exception as e:
            logger.warning(f"Быстрый yt-dlp для stories не сработал: {e}")
            raise

    def _download_instagram_ultra_fast(self, url: str, out_path: str, content_type: str):
        """УЛЬТРА-БЫСТРОЕ скачивание Instagram постов"""
        ydl_opts = self.ultra_fast_ydl_opts.copy()
        ydl_opts['outtmpl'] = os.path.join(out_path, '%(id)s.%(ext)s')
        
        # ОПТИМИЗИРОВАННАЯ НАСТРОЙКА ФОРМАТА
        if content_type == 'video':
            ydl_opts['format'] = 'best[ext=mp4]/best'
        elif content_type == 'photo':
            ydl_opts['format'] = 'best[ext=jpg]/best[ext=png]/best'
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            files = []
            # СУПЕР-БЫСТРЫЙ ПОИСК ФАЙЛОВ
            if info.get('requested_downloads'):
                for download in info['requested_downloads']:
                    file_path = download['filepath']
                    if os.path.exists(file_path) and self._is_media_file_fast(file_path):
                        files.append(file_path)
            
            if not files:
                for file in os.listdir(out_path):
                    file_path = os.path.join(out_path, file)
                    if self._is_media_file_fast(file_path):
                        files.append(file_path)
            
            # БЫСТРОЕ ОПРЕДЕЛЕНИЕ ТИПА КОНТЕНТА
            result_type = 'photo'
            if files:
                first_file = files[0].lower()
                if any(first_file.endswith(ext) for ext in ['.mp4', '.mov', '.avi']):
                    result_type = 'video'
                if len(files) > 1:
                    result_type = 'carousel'
            
            return {
                'type': result_type,
                'files': files,
                'title': info.get('title', 'instagram_content'),
                'webpage_url': info.get('webpage_url', url)
            }

    def _determine_content_type(self, url: str) -> str:
        """Быстрое определение типа контента"""
        if '/reel/' in url or '/reels/' in url or '/tv/' in url:
            return 'video'
        elif '/p/' in url:
            return 'post'
        elif '/stories/' in url:
            return 'story'
        else:
            return 'auto'

    def _is_media_file_fast(self, file_path: str) -> bool:
        """БЫСТРАЯ проверка медиафайла"""
        media_extensions = {'.jpg', '.jpeg', '.png', '.mp4', '.mov', '.avi', '.webm'}
        file_ext = os.path.splitext(file_path)[1].lower()
        return file_ext in media_extensions and os.path.isfile(file_path)

    # FALLBACK МЕТОДЫ
    async def _download_with_instaloader(self, url: str, out_path: str):
        """Резервный метод через instaloader"""
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
            
            shortcode = self._extract_shortcode(url)
            if not shortcode:
                raise Exception("Не удалось извлечь shortcode из URL")
            
            post = instaloader.Post.from_shortcode(L.context, shortcode)
            L.download_post(post, target=out_path)
            
            downloaded_files = []
            for file in os.listdir(out_path):
                file_path = os.path.join(out_path, file)
                if self._is_media_file_fast(file_path):
                    downloaded_files.append(file_path)
            
            result = {
                'type': 'carousel' if post.mediacount > 1 else 'photo',
                'files': downloaded_files,
                'title': f"instagram_{shortcode}",
                'webpage_url': url
            }
            
            if downloaded_files:
                ext = downloaded_files[0].split('.')[-1].lower()
                if ext in ['mp4', 'mov', '.avi']:
                    result['type'] = 'video'
                    
            return result
            
        except Exception as e:
            raise Exception(f"Instaloader ошибка: {str(e)}")

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

# ------------------------- ОПТИМИЗИРОВАННЫЕ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ -------------------------
def extract_first_url(text: str) -> str:
    match = re.search(r"(https?://[^\s]+)", text)
    return match.group(1) if match else ""

def normalize_url(url: str) -> str:
    """Нормализация URL для всех поддерживаемых платформ"""
    # YouTube Shorts
    if "youtube.com/shorts/" in url or "youtu.be/" in url:
        if "youtu.be/" in url:
            video_id = url.split("/")[-1].split("?")[0]
            return f"https://www.youtube.com/watch?v={video_id}"
        return url
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

async def fast_cleanup_directory(dir_path: str):
    """Быстрая очистка директории"""
    try:
        if os.path.exists(dir_path):
            shutil.rmtree(dir_path, ignore_errors=True)
    except Exception as e:
        logger.warning(f"Ошибка очистки: {e}")

def validate_and_fix_extension(file_path: str) -> str:
    """Быстрая проверка и исправление расширения"""
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
                return new_file_path
            except Exception:
                return file_path
    except ImportError:
        pass
    
    return file_path

# ------------------------- ОБНОВЛЕННЫЕ ОБРАБОТЧИКИ СООБЩЕНИЙ -------------------------

@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text(
        "⚡ **ULTRA FAST Downloader** ⚡\n\n"
        "📥 Поддерживаемые платформы:\n"
        "• Instagram: фото, видео, рилсы, карусели, истории\n"
        "• YouTube: видео, Shorts\n\n"
        "🚀 Оптимизировано для максимальной скорости!"
    )

@app.on_message(filters.text & filters.private)
async def handle_text(client, message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    # БЫСТРАЯ ПРОВЕРКА URL
    url = extract_first_url(text)
    if not url:
        return

    # ПРОВЕРКА ДУБЛИРОВАНИЯ
    message_id = f"text_{message.id}_{user_id}"
    if message_id in processed_messages:
        return
    processed_messages.add(message_id)
    
    # ПРОВЕРКА АКТИВНОЙ ОБРАБОТКИ
    if user_processing.get(user_id, {}).get('processing'):
        try:
            temp_msg = await message.reply_text("⚡ Уже обрабатываю...")
            await asyncio.sleep(1)
            await temp_msg.delete()
        except:
            pass
        return

    user_processing[user_id] = {'processing': True}
    status = None
    tmp_dir = None
    
    try:
        url = normalize_url(url)
        logger.info(f"🔄 Обрабатываем URL: {url}")
        
        status = await message.reply_text("⚡ Определяю тип контента...")
        
        if "youtube.com/shorts/" in url or is_youtube_shorts(url):
            # ОБРАБОТКА YOUTUBE SHORTS
            await _handle_youtube_shorts(client, message, url, status)
            
        elif "youtube.com" in url or "youtu.be" in url:
            # ОБЫЧНОЕ YOUTUBE ВИДЕО
            await _handle_youtube_fast(client, message, url, status)
            
        elif "instagram.com" in url:
            # INSTAGRAM КОНТЕНТ
            tmp_dir = tempfile.mkdtemp()
            downloader = InstagramDownloader()
            
            if '/stories/' in url:
                await _handle_instagram_stories(client, message, url, status, downloader, tmp_dir)
            else:
                await _handle_instagram_fast(client, message, url, status, downloader, tmp_dir)

        await message.delete()
        logger.info(f"✅ Обработка завершена для пользователя {user_id}")

    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        try:
            error_msg = await message.reply_text(f"❌ Ошибка: {str(e)[:80]}")
            await asyncio.sleep(3)
            await error_msg.delete()
        except:
            pass
    finally:
        if status:
            try:
                await status.delete()
            except:
                pass
        if tmp_dir:
            await fast_cleanup_directory(tmp_dir)
        user_processing[user_id] = {'processing': False}

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
            await fast_cleanup_directory(tmp_dir)

async def _handle_instagram_stories(client, message, url, status, downloader, tmp_dir):
    """Специальная обработка Instagram Stories"""
    if not check_cookies_file():
        await status.edit_text("❌ Файл cookies.txt не найден.")
        await asyncio.sleep(2)
        return
        
    try:
        await status.edit_text("⚡ Скачиваю Stories...")
        
        content_info = await downloader.download_instagram_content(url, tmp_dir)
        
        if not content_info.get('files'):
            raise Exception("Не удалось скачать Stories")
        
        # БЫСТРАЯ ПРОВЕРКА ФАЙЛОВ
        validated_files = []
        for file_path in content_info['files']:
            if os.path.exists(file_path):
                fixed_path = validate_and_fix_extension(file_path)
                validated_files.append(fixed_path)
        
        content_info['files'] = validated_files
        
        await status.edit_text(f"📤 Отправляю {content_info['type']}...")
        
        # ОТПРАВКА STORIES
        await send_content_fast(client, message, content_info)
        
        logger.info(f"✅ Instagram Stories отправлен ({len(validated_files)} файлов)")
        
    except Exception as e:
        raise e

async def _handle_youtube_fast(client, message, url, status):
    """Обработка обычных YouTube видео"""
    try:
        await status.edit_text("🔗 Получаю прямую ссылку...")
        direct_url = await asyncio.to_thread(get_youtube_direct_url, url)
        
        await status.edit_text("📤 Отправляю видео...")
        await message.reply_video(
            direct_url, 
            caption="📥 YouTube видео через @azams_bot"
        )
        logger.info("✅ YouTube видео отправлено")
        
    except Exception as e:
        logger.warning(f"Прямая ссылка не сработала: {e}")
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
        finally:
            if tmp_dir:
                await fast_cleanup_directory(tmp_dir)

async def _handle_instagram_fast(client, message, url, status, downloader, tmp_dir):
    """Обработка Instagram постов"""
    if not check_cookies_file():
        await status.edit_text("❌ Файл cookies.txt не найден.")
        await asyncio.sleep(2)
        return
        
    try:
        await status.edit_text("⚡ Скачиваю контент...")
        
        content_info = await downloader.download_instagram_content(url, tmp_dir)
        
        if not content_info.get('files'):
            raise Exception("Не удалось скачать файлы")
        
        # БЫСТРАЯ ПРОВЕРКА
        validated_files = []
        for file_path in content_info['files']:
            if os.path.exists(file_path):
                fixed_path = validate_and_fix_extension(file_path)
                validated_files.append(fixed_path)
        
        content_info['files'] = validated_files
        
        await status.edit_text(f"📤 Отправляю {content_info['type']}...")
        
        await send_content_fast(client, message, content_info)
        
        logger.info(f"✅ Instagram {content_info['type']} отправлен")
        
    except Exception as e:
        raise e

async def send_content_fast(client, message, content_info):
    """Универсальная отправка контента"""
    files = content_info['files']
    content_type = content_info['type']
    
    if content_type in ['photo', 'story_photo']:
        # ПАРАЛЛЕЛЬНАЯ ОТПРАВКА ФОТО
        tasks = []
        for file_path in files[:10]:
            if os.path.exists(file_path):
                caption = "📸 Instagram"
                if 'story' in content_type:
                    caption = "📱 Instagram Story"
                
                task = message.reply_photo(file_path, caption=caption)
                tasks.append(task)
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            
    elif content_type in ['video', 'story_video']:
        # ПАРАЛЛЕЛЬНАЯ ОТПРАВКА ВИДЕО
        tasks = []
        for file_path in files[:10]:
            if os.path.exists(file_path):
                caption = "🎬 Instagram"
                if 'story' in content_type:
                    caption = "🎥 Instagram Story"
                
                task = message.reply_video(file_path, caption=caption)
                tasks.append(task)
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            
    elif content_type == 'carousel':
        # ОТПРАВКА КАРУСЕЛИ
        await _send_carousel_fast(client, message, files)

async def _send_carousel_fast(client, message, files):
    """Быстрая отправка карусели"""
    media_group = []
    
    for i, file_path in enumerate(files[:10]):
        if not os.path.exists(file_path):
            continue
            
        try:
            if file_path.lower().endswith(('.jpg', '.jpeg', '.png')):
                media_item = InputMediaPhoto(file_path)
                if i == 0:
                    media_item.caption = "🖼️ Instagram карусель"
                media_group.append(media_item)
                
            elif file_path.lower().endswith(('.mp4', '.mov', '.avi')):
                media_item = InputMediaVideo(file_path)
                if i == 0:
                    media_item.caption = "🎬 Instagram карусель"
                media_group.append(media_item)
        except Exception:
            continue
    
    if media_group:
        try:
            await message.reply_media_group(media_group)
        except Exception:
            # FALLBACK: отправка по одному
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
            except:
                pass
    
    # Проверка cookies
    if os.path.exists("cookies.txt"):
        logger.info("✅ Файл cookies.txt найден")
    else:
        logger.warning("⚠️ Файл cookies.txt не найден")
    
    # Создание директорий
    if not os.path.exists("downloads"):
        os.makedirs("downloads")
    
    logger.info("🚀 ЗАПУСК УЛУЧШЕННОГО БОТА...")
    logger.info("📸 Поддержка: Instagram + YouTube Shorts")
    
    try:
        app.run()
        logger.info("✅ Бот успешно запущен!")
    except Exception as e:
        logger.error(f"❌ Ошибка запуска: {e}")
