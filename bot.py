import os
import asyncio
import logging
import tempfile
import yt_dlp
import re
import time
from pyrogram import Client, filters
from pyrogram.errors import BadRequest, BadMsgNotification
import instaloader
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

# ------------------------- БЫСТРЫЙ Instagram Downloader -------------------------
class InstagramDownloader:
    def __init__(self):
        # БЫСТРЫЕ настройки для видео
        self.video_opts = {
            'outtmpl': 'downloads/%(id)s.%(ext)s',
            'format': 'best[ext=mp4]/best',
            'cookiefile': 'cookies.txt',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'noplaylist': True,
            'socket_timeout': 10,
            'extractretry': 1,
            'retries': 1,
            'fragment_retries': 1,
            'skip_unavailable_fragments': True,
            'keep_fragments': False,
            'concurrent_fragment_downloads': 8,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15',
                'Accept': '*/*',
                'Accept-Encoding': 'gzip, deflate, br',
            }
        }
        
        # БЫСТРЫЕ настройки для фото
        self.photo_opts = {
            'outtmpl': 'downloads/%(id)s.%(ext)s',
            'format': 'best[ext=jpg]/best[ext=png]/best',
            'cookiefile': 'cookies.txt',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'noplaylist': True,
            'socket_timeout': 10,
            'extractretry': 1,
            'retries': 1,
            'fragment_retries': 1,
            'skip_unavailable_fragments': True,
            'keep_fragments': False,
            'concurrent_fragment_downloads': 8,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15',
                'Accept': '*/*',
                'Accept-Encoding': 'gzip, deflate, br',
            }
        }
        
        self.thread_pool = ThreadPoolExecutor(max_workers=2)

    async def download_content(self, url: str, out_path: str):
        """Определяет тип контента и скачивает ТОЛЬКО его"""
        try:
            # Сначала определяем тип контента
            content_type = await self._detect_content_type(url)
            logger.info(f"🔍 Определен тип контента: {content_type}")
            
            # Скачиваем ТОЛЬКО нужный тип контента
            if content_type == 'video':
                return await self._download_video_only(url, out_path)
            elif content_type == 'photo':
                return await self._download_photo_only(url, out_path)
            else:
                return await self._download_fallback(url, out_path)
                
        except Exception as e:
            logger.error(f"❌ Ошибка скачивания: {e}")
            raise

    async def _detect_content_type(self, url: str) -> str:
        """Быстро определяет тип контента по URL"""
        loop = asyncio.get_event_loop()
        
        # Анализируем URL для быстрого определения
        if '/reel/' in url or '/reels/' in url or '/tv/' in url:
            return 'video'
        elif '/p/' in url:
            # Для постов нужно проверить что внутри
            try:
                return await loop.run_in_executor(
                    self.thread_pool,
                    self._check_post_content_type,
                    url
                )
            except:
                return 'photo'  # По умолчанию для постов
        elif '/stories/' in url:
            return 'video'  # Истории обычно видео
        else:
            return 'photo'

    def _check_post_content_type(self, url: str) -> str:
        """Проверяет тип контента в посте"""
        ydl_opts = {
            'skip_download': True,
            'quiet': True,
            'no_warnings': True,
            'cookiefile': 'cookies.txt'
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Проверяем длительность - если есть, то видео
            if info.get('duration') and info['duration'] > 0:
                return 'video'
            
            # Проверяем расширение
            if info.get('ext'):
                ext = info['ext'].lower()
                if ext in ['mp4', 'mov', 'avi', 'webm']:
                    return 'video'
                elif ext in ['jpg', 'jpeg', 'png']:
                    return 'photo'
            
            return 'photo'

    async def _download_video_only(self, url: str, out_path: str):
        """Скачивает ТОЛЬКО видео"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.thread_pool,
            self._download_video_only_sync,
            url, out_path
        )

    def _download_video_only_sync(self, url: str, out_path: str):
        """Синхронное скачивание видео"""
        opts = self.video_opts.copy()
        opts['outtmpl'] = os.path.join(out_path, 'video_%(id)s.%(ext)s')
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            # Ищем скачанный видео файл
            for file in os.listdir(out_path):
                if file.startswith('video_') and file.lower().endswith(('.mp4', '.mov', '.avi', '.webm')):
                    file_path = os.path.join(out_path, file)
                    return {
                        'type': 'video',
                        'files': [file_path],
                        'webpage_url': url
                    }
            
            raise Exception("Видео файл не найден после скачивания")

    async def _download_photo_only(self, url: str, out_path: str):
        """Скачивает ТОЛЬКО фото"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.thread_pool,
            self._download_photo_only_sync,
            url, out_path
        )

    def _download_photo_only_sync(self, url: str, out_path: str):
        """Синхронное скачивание фото"""
        opts = self.photo_opts.copy()
        opts['outtmpl'] = os.path.join(out_path, 'photo_%(id)s.%(ext)s')
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            # Ищем скачанные фото файлы (максимум 10)
            photo_files = []
            for file in os.listdir(out_path):
                if file.startswith('photo_') and file.lower().endswith(('.jpg', '.jpeg', '.png')):
                    file_path = os.path.join(out_path, file)
                    photo_files.append(file_path)
                    if len(photo_files) >= 10:  # Ограничиваем количество
                        break
            
            if not photo_files:
                raise Exception("Фото файлы не найдены после скачивания")
            
            return {
                'type': 'photo',
                'files': photo_files,
                'webpage_url': url
            }

    async def _download_fallback(self, url: str, out_path: str):
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
                raise Exception("Не удалось извлечь shortcode")
            
            post = instaloader.Post.from_shortcode(L.context, shortcode)
            L.download_post(post, target=out_path)
            
            # Собираем скачанные файлы
            downloaded_files = []
            for file in os.listdir(out_path):
                file_path = os.path.join(out_path, file)
                if self._is_media_file(file_path):
                    downloaded_files.append(file_path)
            
            if not downloaded_files:
                raise Exception("Не удалось скачать файлы")
            
            return {
                'type': 'mixed',
                'files': downloaded_files[:10],  # Ограничиваем количество
                'webpage_url': url
            }
            
        except Exception as e:
            raise Exception(f"Instaloader ошибка: {str(e)}")

    def _is_media_file(self, file_path: str) -> bool:
        """Проверяет, является ли файл медиафайлом"""
        media_extensions = ['.jpg', '.jpeg', '.png', '.mp4', '.mov', '.avi', '.webm']
        file_ext = os.path.splitext(file_path)[1].lower()
        return file_ext in media_extensions and os.path.isfile(file_path)

    def _extract_shortcode(self, url: str):
        """Извлекает shortcode из URL Instagram"""
        patterns = [
            r'instagram\.com/p/([^/?]+)',
            r'instagram\.com/reel/([^/?]+)',
            r'instagram\.com/stories/([^/?]+)/([^/?]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1) if match.lastindex >= 1 else match.group(0)
        return None

# ------------------------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ -------------------------
def extract_first_url(text: str) -> str:
    match = re.search(r"(https?://[^\s]+)", text)
    return match.group(1) if match else ""

def check_cookies_file():
    return os.path.exists("cookies.txt")

def cleanup_old_processed_messages():
    global processed_messages
    if len(processed_messages) > 1000:
        processed_messages = set(list(processed_messages)[-500:])

def safe_remove_directory(dir_path: str):
    try:
        if os.path.exists(dir_path):
            shutil.rmtree(dir_path)
    except Exception as e:
        logger.warning(f"⚠️ Не удалось удалить директорию: {e}")

# ------------------------- ОБРАБОТЧИКИ СООБЩЕНИЙ -------------------------

@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text(
        "⚡ **Instagram Downloader** ⚡\n\n"
        "📥 Отправь ссылку на Instagram\n"
        "• Видео, фото, рилсы\n"
        "• Быстро и без лишних сообщений"
    )

@app.on_message(filters.text & filters.private)
async def handle_text(client, message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    # Пропускаем команды
    if text.startswith('/'):
        return
    
    url = extract_first_url(text)
    if not url or "instagram.com" not in url:
        return

    message_id = f"text_{message.id}_{user_id}"
    if message_id in processed_messages:
        return
    processed_messages.add(message_id)
    
    # Проверяем что пользователь не занят
    if user_id in user_processing and user_processing[user_id].get('processing'):
        return

    user_processing[user_id] = {'processing': True}
    tmp_dir = None
    
    try:
        # Создаем временную директорию
        tmp_dir = tempfile.mkdtemp()
        downloader = InstagramDownloader()
        
        # Проверяем cookies
        if not check_cookies_file():
            return
        
        # Скачиваем контент
        content_info = await downloader.download_content(url, tmp_dir)
        
        if not content_info.get('files'):
            return
        
        # Отправляем контент БЕЗ лишних сообщений
        await send_content_silent(client, message, content_info)
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
    finally:
        # Очистка
        if tmp_dir:
            safe_remove_directory(tmp_dir)
        if user_id in user_processing:
            user_processing[user_id]['processing'] = False
        cleanup_old_processed_messages()

async def send_content_silent(client, message, content_info):
    """Отправляет контент БЕЗ лишних сообщений"""
    files = content_info.get('files', [])
    content_type = content_info.get('type', 'unknown')
    
    if not files:
        return
    
    # Отправляем в зависимости от типа контента
    if content_type == 'video':
        # Отправляем первое видео
        video_path = files[0]
        if os.path.exists(video_path):
            await message.reply_video(video_path)
            
    elif content_type == 'photo':
        # Отправляем все фото (до 10) как медиагруппу
        photo_files = files[:10]
        if len(photo_files) == 1:
            # Одно фото - отправляем отдельно
            await message.reply_photo(photo_files[0])
        else:
            # Несколько фото - отправляем группой
            from pyrogram.types import InputMediaPhoto
            media_group = []
            for i, photo_path in enumerate(photo_files):
                if os.path.exists(photo_path):
                    media_item = InputMediaPhoto(photo_path)
                    media_group.append(media_item)
            
            if media_group:
                await message.reply_media_group(media_group)
    
    else:
        # Смешанный контент - отправляем первое что найдем
        for file_path in files[:3]:
            if os.path.exists(file_path):
                if file_path.lower().endswith(('.mp4', '.mov', '.avi', '.webm')):
                    await message.reply_video(file_path)
                    break
                elif file_path.lower().endswith(('.jpg', '.jpeg', '.png')):
                    await message.reply_photo(file_path)
                    break

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
    if not os.path.exists("cookies.txt"):
        logger.warning("⚠️ Файл cookies.txt не найден")
    
    # Создание директорий
    if not os.path.exists("downloads"):
        os.makedirs("downloads")
    
    logger.info("🚀 ЗАПУСК БЫСТРОГО БОТА...")
    
    try:
        app.run()
    except Exception as e:
        logger.error(f"❌ Ошибка запуска: {e}")
