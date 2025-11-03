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

# ------------------------- ОПТИМИЗИРОВАННЫЙ КЛИЕНТ -------------------------
app = Client(
    "video_bot_new_session_2024",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    sleep_threshold=30,
    workers=100,
)

# ------------------------- ИСПРАВЛЕННЫЙ Instagram Downloader -------------------------
class InstagramDownloader:
    def __init__(self):
        # ОПТИМИЗИРОВАННЫЕ НАСТРОЙКИ ДЛЯ INSTAGRAM
        self.instagram_ydl_opts = {
            'outtmpl': 'downloads/%(id)s.%(ext)s',
            'format': 'best[height<=720]',
            'cookiefile': 'cookies.txt',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'noplaylist': True,
            
            # ⚡ ОПТИМИЗАЦИИ СКОРОСТИ ⚡
            'socket_timeout': 15,
            'extractretry': 1,
            'retries': 2,
            'fragment_retries': 2,
            'skip_unavailable_fragments': True,
            'keep_fragments': False,
            'concurrent_fragment_downloads': 6,
            
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15',
                'Accept': '*/*',
                'Accept-Encoding': 'gzip, deflate, br',
                'Origin': 'https://www.instagram.com',
                'Referer': 'https://www.instagram.com/',
            }
        }
        
        # ОТДЕЛЬНЫЕ НАСТРОЙКИ ДЛЯ YOUTUBE (БЕЗ COOKIES ДЛЯ ИЗБЕЖАНИЯ ОШИБКИ АВТОРИЗАЦИИ)
        self.youtube_ydl_opts = {
            'outtmpl': 'downloads/%(id)s.%(ext)s',
            'format': 'best[height<=720]',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'noplaylist': True,
            
            # НАСТРОЙКИ ДЛЯ ОБХОДА ОШИБКИ АВТОРИЗАЦИИ
            'socket_timeout': 10,
            'extractretry': 1,
            'retries': 1,
            'fragment_retries': 1,
            'skip_unavailable_fragments': True,
            
            # НЕ ИСПОЛЬЗУЕМ COOKIES ДЛЯ YOUTUBE
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': '*/*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
            }
        }
        
        self.thread_pool = ThreadPoolExecutor(max_workers=3)

    async def download_instagram_content(self, url: str, out_path: str):
        """УНИВЕРСАЛЬНАЯ функция для скачивания Instagram контента"""
        try:
            loop = asyncio.get_event_loop()
            
            # ДЛЯ STORIES ИСПОЛЬЗУЕМ ТОЛЬКО yt-dlp (ИЗБЕГАЕМ INSTALOADER)
            if '/stories/' in url:
                result = await loop.run_in_executor(
                    self.thread_pool, 
                    self._download_instagram_with_ytdlp, 
                    url, out_path, 'story'
                )
            else:
                result = await loop.run_in_executor(
                    self.thread_pool,
                    self._download_instagram_with_ytdlp,
                    url, out_path, 'post'
                )
            return result
            
        except Exception as e:
            logger.error(f"Ошибка скачивания Instagram: {e}")
            raise Exception(f"Не удалось скачать Instagram контент: {str(e)}")

    def _download_instagram_with_ytdlp(self, url: str, out_path: str, content_type: str):
        """Скачивание Instagram контента через yt-dlp (ОСНОВНОЙ МЕТОД)"""
        ydl_opts = self.instagram_ydl_opts.copy()
        
        if content_type == 'story':
            ydl_opts['outtmpl'] = os.path.join(out_path, 'story_%(id)s.%(ext)s')
        else:
            ydl_opts['outtmpl'] = os.path.join(out_path, '%(id)s.%(ext)s')
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                files = []
                # БЫСТРЫЙ ПОИСК ФАЙЛОВ
                if info.get('requested_downloads'):
                    for download in info['requested_downloads']:
                        file_path = download['filepath']
                        if os.path.exists(file_path) and self._is_media_file(file_path):
                            files.append(file_path)
                
                # ЕСЛИ ФАЙЛЫ НЕ НАЙДЕНЫ, ИЩЕМ В ДИРЕКТОРИИ
                if not files:
                    for file in os.listdir(out_path):
                        file_path = os.path.join(out_path, file)
                        if self._is_media_file(file_path):
                            files.append(file_path)
                
                # ОПРЕДЕЛЯЕМ ТИП КОНТЕНТА
                result_type = 'photo'
                if files:
                    first_file = files[0].lower()
                    if any(first_file.endswith(ext) for ext in ['.mp4', '.mov', '.avi']):
                        result_type = 'video'
                    if len(files) > 1:
                        result_type = 'carousel'
                
                # ДЛЯ STORIES УКАЗЫВАЕМ ТИП
                if content_type == 'story':
                    if result_type == 'video':
                        result_type = 'story_video'
                    else:
                        result_type = 'story_photo'
                
                return {
                    'type': result_type,
                    'files': files,
                    'title': info.get('title', 'instagram_content'),
                    'webpage_url': info.get('webpage_url', url)
                }
                
        except Exception as e:
            logger.error(f"Ошибка yt-dlp для Instagram: {e}")
            raise

    async def download_youtube_shorts(self, url: str, out_path: str):
        """Скачивание YouTube Shorts (ИСПРАВЛЕННАЯ ВЕРСИЯ)"""
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
            # ПРОБУЕМ АЛЬТЕРНАТИВНЫЙ МЕТОД
            try:
                result = await loop.run_in_executor(
                    self.thread_pool,
                    self._download_youtube_alternative,
                    url, out_path
                )
                return result
            except Exception as alt_error:
                raise Exception(f"Не удалось скачать YouTube Shorts: {str(alt_error)}")

    def _download_youtube_shorts_fast(self, url: str, out_path: str):
        """ОСНОВНОЙ МЕТОД СКАЧИВАНИЯ YOUTUBE SHORTS"""
        ydl_opts = self.youtube_ydl_opts.copy()
        ydl_opts['outtmpl'] = os.path.join(out_path, 'shorts_%(id)s.%(ext)s')
        
        # ДОБАВЛЯЕМ НАСТРОЙКИ ДЛЯ ОБХОДА ОШИБКИ АВТОРИЗАЦИИ
        ydl_opts.update({
            'no_check_certificate': True,
            'prefer_insecure': True,
            'geo_bypass': True,
            'geo_bypass_country': 'US',
        })
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                # ПОИСК СКАЧАННОГО ФАЙЛА
                file_path = None
                if info.get('requested_downloads'):
                    for download in info['requested_downloads']:
                        if os.path.exists(download['filepath']):
                            file_path = download['filepath']
                            break
                
                if not file_path:
                    for file in os.listdir(out_path):
                        if file.startswith('shorts_') and (file.endswith('.mp4') or file.endswith('.webm')):
                            file_path = os.path.join(out_path, file)
                            break
                
                if not file_path:
                    raise Exception("Не удалось найти скачанный файл")
                
                return {
                    'type': 'video',
                    'files': [file_path],
                    'title': info.get('title', 'youtube_shorts'),
                    'webpage_url': url
                }
                
        except Exception as e:
            logger.error(f"Основной метод YouTube не сработал: {e}")
            raise

    def _download_youtube_alternative(self, url: str, out_path: str):
        """АЛЬТЕРНАТИВНЫЙ МЕТОД ДЛЯ YOUTUBE (ЕСЛИ ОСНОВНОЙ НЕ РАБОТАЕТ)"""
        # ПРОБУЕМ СКАЧАТЬ БЕЗ COOKIES И С ДРУГИМИ НАСТРОЙКАМИ
        ydl_opts = {
            'outtmpl': os.path.join(out_path, 'shorts_%(id)s.%(ext)s'),
            'format': 'worst[height<=480]/worst',  # НИЗКОЕ КАЧЕСТВО - МЕНЬШЕ ПРОБЛЕМ
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 15,
            'retries': 1,
            'no_check_certificate': True,
            'prefer_insecure': True,
            'geo_bypass': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36',
                'Accept': '*/*',
                'Accept-Language': 'en-US,en;q=0.5',
            }
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                # ПОИСК ФАЙЛА
                for file in os.listdir(out_path):
                    if file.startswith('shorts_') and os.path.isfile(os.path.join(out_path, file)):
                        file_path = os.path.join(out_path, file)
                        return {
                            'type': 'video',
                            'files': [file_path],
                            'title': info.get('title', 'youtube_shorts'),
                            'webpage_url': url
                        }
                
                raise Exception("Файл не найден после скачивания")
                
        except Exception as e:
            logger.error(f"Альтернативный метод YouTube не сработал: {e}")
            raise

    def _is_media_file(self, file_path: str) -> bool:
        """Проверка медиафайла"""
        media_extensions = {'.jpg', '.jpeg', '.png', '.mp4', '.mov', '.avi', '.webm'}
        file_ext = os.path.splitext(file_path)[1].lower()
        return file_ext in media_extensions and os.path.isfile(file_path)

# ------------------------- ОПТИМИЗИРОВАННЫЕ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ -------------------------
def extract_first_url(text: str) -> str:
    match = re.search(r"(https?://[^\s]+)", text)
    return match.group(1) if match else ""

def normalize_url(url: str) -> str:
    """Нормализация URL"""
    # YouTube Shorts
    if "youtube.com/shorts/" in url or "youtu.be/" in url:
        if "youtu.be/" in url:
            video_id = url.split("/")[-1].split("?")[0]
            return f"https://www.youtube.com/watch?v={video_id}"
    return url

def is_youtube_shorts(url: str) -> bool:
    """Проверка YouTube Shorts"""
    return "youtube.com/shorts/" in url or ("youtu.be/" in url and len(url.split("/")[-1]) == 11)

def check_cookies_file():
    if not os.path.exists("cookies.txt"):
        logger.error("❌ Файл cookies.txt не найден! Instagram может не работать")
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

# ------------------------- ОБНОВЛЕННЫЕ ОБРАБОТЧИКИ -------------------------

@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text(
        "⚡ **ИСПРАВЛЕННЫЙ Downloader** ⚡\n\n"
        "📥 Теперь работает:\n"
        "• Instagram: фото, видео, рилсы, карусели, истории\n"
        "• YouTube: видео, Shorts\n\n"
        "🚀 Исправлены ошибки скачивания!"
    )

@app.on_message(filters.text & filters.private)
async def handle_text(client, message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    # ПРОВЕРКА URL
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
        
        if is_youtube_shorts(url):
            # YOUTUBE SHORTS
            await _handle_youtube_shorts(client, message, url, status)
            
        elif "youtube.com" in url or "youtu.be" in url:
            # ОБЫЧНОЕ YOUTUBE ВИДЕО
            await _handle_youtube_video(client, message, url, status)
            
        elif "instagram.com" in url:
            # INSTAGRAM
            tmp_dir = tempfile.mkdtemp()
            downloader = InstagramDownloader()
            
            if '/stories/' in url:
                await _handle_instagram_stories(client, message, url, status, downloader, tmp_dir)
            else:
                await _handle_instagram_post(client, message, url, status, downloader, tmp_dir)

        await message.delete()
        logger.info(f"✅ Обработка завершена для пользователя {user_id}")

    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        try:
            error_msg = await message.reply_text(f"❌ Ошибка: {str(e)[:100]}")
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
            caption="🎬 YouTube Shorts"
        )
        
        logger.info("✅ YouTube Shorts отправлен")
        
    except Exception as e:
        raise e
    finally:
        if tmp_dir:
            await fast_cleanup_directory(tmp_dir)

async def _handle_youtube_video(client, message, url, status):
    """Обработка обычных YouTube видео"""
    try:
        await status.edit_text("⚡ Скачиваю YouTube видео...")
        tmp_dir = tempfile.mkdtemp()
        
        downloader = InstagramDownloader()
        content_info = await downloader.download_youtube_shorts(url, tmp_dir)  # Используем тот же метод
        
        if not content_info.get('files'):
            raise Exception("Не удалось скачать видео")
        
        await status.edit_text("📤 Отправляю видео...")
        
        file_path = content_info['files'][0]
        await message.reply_video(
            file_path,
            caption="📹 YouTube видео"
        )
        
        logger.info("✅ YouTube видео отправлено")
        
    except Exception as e:
        raise e
    finally:
        if tmp_dir:
            await fast_cleanup_directory(tmp_dir)

async def _handle_instagram_stories(client, message, url, status, downloader, tmp_dir):
    """Обработка Instagram Stories"""
    if not check_cookies_file():
        await status.edit_text("⚠️ Файл cookies.txt не найден. Instagram может не работать.")
        await asyncio.sleep(2)
    
    try:
        await status.edit_text("⚡ Скачиваю Stories...")
        
        content_info = await downloader.download_instagram_content(url, tmp_dir)
        
        if not content_info.get('files'):
            raise Exception("Не удалось скачать Stories")
        
        await status.edit_text(f"📤 Отправляю {content_info['type']}...")
        
        # ОТПРАВКА CONTENT
        await send_content_fast(client, message, content_info)
        
        logger.info(f"✅ Instagram Stories отправлен")
        
    except Exception as e:
        raise e

async def _handle_instagram_post(client, message, url, status, downloader, tmp_dir):
    """Обработка Instagram постов"""
    if not check_cookies_file():
        await status.edit_text("⚠️ Файл cookies.txt не найден. Instagram может не работать.")
        await asyncio.sleep(2)
    
    try:
        await status.edit_text("⚡ Скачиваю контент...")
        
        content_info = await downloader.download_instagram_content(url, tmp_dir)
        
        if not content_info.get('files'):
            raise Exception("Не удалось скачать контент")
        
        await status.edit_text(f"📤 Отправляю {content_info['type']}...")
        
        await send_content_fast(client, message, content_info)
        
        logger.info(f"✅ Instagram контент отправлен")
        
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
        logger.warning("⚠️ Файл cookies.txt не найден - Instagram может не работать")
    
    # Создание директорий
    if not os.path.exists("downloads"):
        os.makedirs("downloads")
    
    logger.info("🚀 ЗАПУСК ИСПРАВЛЕННОГО БОТА...")
    logger.info("🔧 Исправлены: Instagram Stories + YouTube Shorts")
    
    try:
        app.run()
        logger.info("✅ Бот успешно запущен!")
    except Exception as e:
        logger.error(f"❌ Ошибка запуска: {e}")
