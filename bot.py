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

# ------------------------- ИСПРАВЛЕННЫЙ Instagram Downloader -------------------------
class InstagramDownloader:
    def __init__(self):
        self.fast_ydl_opts = {
            'outtmpl': 'downloads/%(id)s.%(ext)s',
            'format': 'bestvideo+bestaudio/best[height<=1080]/best',
            'cookiefile': 'cookies.txt',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'noplaylist': True,
            'socket_timeout': 15,
            'extractretry': 1,
            'retries': 2,
            'fragment_retries': 2,
            'skip_unavailable_fragments': True,
            'keep_fragments': False,
            'concurrent_fragment_downloads': 6,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': '*/*',
                'Accept-Encoding': 'gzip, deflate, br',
            }
        }
        self.thread_pool = ThreadPoolExecutor(max_workers=3)

    async def download_instagram_content(self, url: str, out_path: str):
        """ОПТИМИЗИРОВАННАЯ функция для скачивания только нужного типа контента"""
        try:
            loop = asyncio.get_event_loop()
            
            # Сначала определяем реальный тип контента
            content_type = await self._determine_real_content_type(url)
            logger.info(f"🔍 Определен реальный тип контента: {content_type}")
            
            if '/stories/' in url:
                result = await loop.run_in_executor(
                    self.thread_pool, 
                    self._download_story_fast, 
                    url, out_path, content_type
                )
            else:
                result = await loop.run_in_executor(
                    self.thread_pool,
                    self._download_with_ytdlp_fast,
                    url, out_path, content_type
                )
            
            # Фильтруем файлы по типу контента
            result = self._filter_files_by_content_type(result)
            return result
            
        except Exception as e:
            logger.warning(f"Быстрый метод не сработал: {e}, пробуем instaloader")
            return await self._download_with_instaloader(url, out_path)

    async def _determine_real_content_type(self, url: str) -> str:
        """ОПРЕДЕЛЕНИЕ РЕАЛЬНОГО ТИПА КОНТЕНТА БЕЗ СКАЧИВАНИЯ"""
        try:
            loop = asyncio.get_event_loop()
            
            # Используем yt-dlp для получения информации без скачивания
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'cookiefile': 'cookies.txt',
            }
            
            def get_info():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(url, download=False)
            
            info = await loop.run_in_executor(self.thread_pool, get_info)
            
            # Анализируем информацию для определения типа
            if info.get('_type') == 'playlist':
                entries = info.get('entries', [])
                if entries:
                    first_entry = entries[0]
                    if first_entry.get('url'):
                        # Рекурсивно проверяем первый элемент
                        return await self._determine_real_content_type(first_entry['url'])
                    elif first_entry.get('formats'):
                        return self._analyze_formats(first_entry.get('formats', []))
            
            # Анализируем форматы
            if info.get('formats'):
                return self._analyze_formats(info.get('formats', []))
            
            # Резервное определение по URL
            return self._determine_content_type_by_url(url)
            
        except Exception as e:
            logger.warning(f"Не удалось определить тип контента: {e}, используем резервный метод")
            return self._determine_content_type_by_url(url)

    def _analyze_formats(self, formats: list) -> str:
        """АНАЛИЗ ФОРМАТОВ ДЛЯ ОПРЕДЕЛЕНИЯ ТИПА КОНТЕНТА"""
        has_video = any(f.get('vcodec') != 'none' for f in formats)
        has_audio = any(f.get('acodec') != 'none' for f in formats)
        
        # Если есть видео-кодек, считаем что это видео
        if has_video:
            return 'video'
        # Если есть только аудио и изображения - это фото
        elif has_audio and not has_video:
            return 'photo'
        else:
            return 'photo'

    def _determine_content_type_by_url(self, url: str) -> str:
        """Резервное определение типа по URL"""
        if any(x in url for x in ['/reel/', '/reels/', '/tv/', '/video/']):
            return 'video'
        elif '/stories/' in url:
            return 'story'
        elif '/p/' in url:
            return 'post'
        else:
            return 'video'

    def _filter_files_by_content_type(self, result: dict) -> dict:
        """ФИЛЬТРАЦИЯ ФАЙЛОВ ПО ТИПУ КОНТЕНТА"""
        if not result.get('files'):
            return result
            
        content_type = result.get('type', 'unknown')
        video_files = [f for f in result['files'] if self._is_video_file(f)]
        photo_files = [f for f in result['files'] if self._is_photo_file(f)]
        
        logger.info(f"📊 До фильтрации: {len(video_files)} видео, {len(photo_files)} фото")
        
        # ⚠️ ВАЖНО: Фильтруем файлы в зависимости от типа контента
        if content_type in ['video', 'story_video']:
            # Для видео оставляем ТОЛЬКО видео файлы
            result['files'] = video_files
            if not result['files']:
                logger.warning("⚠️ Нет видео файлов после фильтрации!")
                
        elif content_type in ['photo', 'story_photo']:
            # Для фото оставляем ТОЛЬКО фото файлы
            result['files'] = photo_files
            if not result['files']:
                logger.warning("⚠️ Нет фото файлов после фильтрации!")
                
        elif content_type == 'carousel':
            # Для карусели оставляем все файлы (и фото и видео)
            # Но можно добавить дополнительную логику если нужно
            pass
        
        logger.info(f"📊 После фильтрации: {len(result['files'])} файлов")
        return result

    def _download_story_fast(self, url: str, out_path: str, content_type: str):
        """ОПТИМИЗИРОВАННОЕ скачивание историй"""
        try:
            ydl_opts = self.fast_ydl_opts.copy()
            ydl_opts['outtmpl'] = os.path.join(out_path, 'story_%(id)s.%(ext)s')
            
            # Настраиваем формат в зависимости от типа контента
            if content_type == 'video':
                ydl_opts['format'] = 'bestvideo+bestaudio/best[height<=1080]/best'
            else:
                ydl_opts['format'] = 'best[ext=jpg]/best[ext=png]/best'
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                result = {
                    'type': 'story',
                    'files': [],
                    'title': f"instagram_story_{info.get('id', 'unknown')}",
                    'webpage_url': url
                }
                
                # Собираем скачанные файлы
                if info.get('requested_downloads'):
                    for download in info['requested_downloads']:
                        file_path = download['filepath']
                        if os.path.exists(file_path) and self._is_media_file_fast(file_path):
                            result['files'].append(file_path)
                
                if not result['files']:
                    for file in os.listdir(out_path):
                        file_path = os.path.join(out_path, file)
                        if self._is_media_file_fast(file_path):
                            result['files'].append(file_path)
                
                # Определяем окончательный тип
                if result['files']:
                    video_count = sum(1 for f in result['files'] if self._is_video_file(f))
                    if video_count > 0:
                        result['type'] = 'story_video'
                    else:
                        result['type'] = 'story_photo'
                
                return result
                
        except Exception as e:
            logger.warning(f"Быстрый yt-dlp для историй не сработал: {e}")
            raise

    def _download_with_ytdlp_fast(self, url: str, out_path: str, content_type: str):
        """ИСПРАВЛЕННОЕ скачивание через yt-dlp с правильными форматами"""
        ydl_opts = self.fast_ydl_opts.copy()
        ydl_opts['outtmpl'] = os.path.join(out_path, '%(id)s.%(ext)s')
        
        # ⚠️ ВАЖНО: Настраиваем формат в зависимости от типа контента
        if content_type == 'video':
            ydl_opts['format'] = 'bestvideo+bestaudio/best[height<=1080]/best'
            ydl_opts['writethumbnail'] = False  # ⚠️ Не скачивать обложки
        elif content_type == 'photo':
            ydl_opts['format'] = 'best[ext=jpg]/best[ext=png]/best'
            ydl_opts['writethumbnail'] = False  # ⚠️ Не скачивать обложки
        else:  # post, carousel
            # Для постов и каруселей скачиваем все
            ydl_opts['format'] = 'bestvideo+bestaudio/best[height<=1080]/best/best[ext=jpg]/best[ext=png]'
        
        logger.info(f"🎯 Используем формат для {content_type}: {ydl_opts['format']}")
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            result = {
                'type': 'unknown',
                'files': [],
                'title': info.get('title', 'instagram_content'),
                'webpage_url': info.get('webpage_url', url),
            }
            
            # Собираем ТОЛЬКО основные скачанные файлы (не обложки)
            if info.get('requested_downloads'):
                for download in info['requested_downloads']:
                    file_path = download['filepath']
                    if os.path.exists(file_path) and self._is_media_file_fast(file_path):
                        # Пропускаем файлы обложек
                        if not self._is_thumbnail_file(file_path):
                            result['files'].append(file_path)
            
            # Если не нашли через requested_downloads, ищем в директории
            if not result['files']:
                for file in os.listdir(out_path):
                    file_path = os.path.join(out_path, file)
                    if self._is_media_file_fast(file_path) and not self._is_thumbnail_file(file_path):
                        result['files'].append(file_path)
            
            # Определяем окончательный тип на основе скачанных файлов
            video_files = [f for f in result['files'] if self._is_video_file(f)]
            photo_files = [f for f in result['files'] if self._is_photo_file(f)]
            
            logger.info(f"📁 Скачано файлов: {len(result['files'])} (видео: {len(video_files)}, фото: {len(photo_files)})")
            
            if info.get('_type') == 'playlist' or len(result['files']) > 1:
                result['type'] = 'carousel'
            else:
                if video_files:
                    result['type'] = 'video'
                elif photo_files:
                    result['type'] = 'photo'
                else:
                    # Резервное определение по расширению
                    if result['files']:
                        ext = result['files'][0].split('.')[-1].lower()
                        if ext in ['jpg', 'png', 'jpeg']:
                            result['type'] = 'photo'
                        elif ext in ['mp4', 'mov', 'avi']:
                            result['type'] = 'video'
            
            return result

    def _is_thumbnail_file(self, file_path: str) -> bool:
        """Проверяет, является ли файл обложкой/миниатюрой"""
        filename = os.path.basename(file_path).lower()
        # Паттерны для файлов обложек
        thumbnail_patterns = [
            'thumbnail', 'thumb', 'cover', 'poster', 
            'miniature', 'miniatura', '_thumb', '-thumb'
        ]
        return any(pattern in filename for pattern in thumbnail_patterns)

    def _is_media_file_fast(self, file_path: str) -> bool:
        """БЫСТРАЯ проверка медиафайла"""
        media_extensions = {'.jpg', '.jpeg', '.png', '.mp4', '.mov', '.avi', '.webm'}
        file_ext = os.path.splitext(file_path)[1].lower()
        return file_ext in media_extensions and os.path.isfile(file_path)

    def _is_video_file(self, file_path: str) -> bool:
        """Проверяет, является ли файл видео"""
        video_extensions = {'.mp4', '.mov', '.avi', '.webm', '.mkv'}
        file_ext = os.path.splitext(file_path)[1].lower()
        
        if file_ext in video_extensions:
            return True
        
        # Дополнительная проверка через filetype
        try:
            import filetype
            kind = filetype.guess(file_path)
            return kind and kind.mime.startswith('video/')
        except:
            return file_ext in video_extensions

    def _is_photo_file(self, file_path: str) -> bool:
        """Проверяет, является ли файл фото"""
        photo_extensions = {'.jpg', '.jpeg', '.png', '.webp'}
        file_ext = os.path.splitext(file_path)[1].lower()
        
        if file_ext in photo_extensions:
            return True
        
        # Дополнительная проверка через filetype
        try:
            import filetype
            kind = filetype.guess(file_path)
            return kind and kind.mime.startswith('image/')
        except:
            return file_ext in photo_extensions

    async def _download_with_instaloader(self, url: str, out_path: str):
        """Fallback метод через instaloader"""
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
                if self._is_media_file_fast(file_path) and not self._is_thumbnail_file(file_path):
                    downloaded_files.append(file_path)
            
            result = {
                'type': 'carousel' if post.mediacount > 1 else 'photo',
                'files': downloaded_files,
                'title': f"instagram_{shortcode}",
                'webpage_url': url
            }
            
            # Определяем тип на основе скачанных файлов
            video_files = [f for f in downloaded_files if self._is_video_file(f)]
            if video_files:
                if len(video_files) == 1 and len(downloaded_files) == 1:
                    result['type'] = 'video'
                else:
                    result['type'] = 'carousel'
                    
            return result
            
        except Exception as e:
            raise Exception(f"Instaloader ошибка: {str(e)}")

    def _extract_shortcode(self, url: str):
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

# ------------------------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ -------------------------
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
            "📥 Отправь ссылку из Instagram — я скачаю контент:\n"
            "• Видео - только видео\n" 
            "• Фото - только фото\n"
            "• Карусель - все медиафайлы\n"
            "⚡ Автоматически определяет тип контента!"
        )
        logger.info(f"✅ Отправлено приветственное сообщение пользователю {message.from_user.id}")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки приветствия: {e}")
    
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
        
        if "instagram.com" in url:
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

async def _handle_instagram_fast(client, message, url, status, downloader, tmp_dir):
    """ОПТИМИЗИРОВАННАЯ обработка Instagram"""
    if not check_cookies_file():
        await status.edit_text("❌ Файл cookies.txt не найден. Instagram недоступен.")
        await asyncio.sleep(3)
        return
        
    try:
        await status.edit_text("⚡ Определяю тип контента...")
        
        # Определяем тип контента перед скачиванием
        content_type = await downloader._determine_real_content_type(url)
        type_messages = {
            'video': '🎥 Видео',
            'photo': '🖼️ Фото', 
            'story_video': '📹 Видео-история',
            'story_photo': '📸 Фото-история',
            'carousel': '🔄 Карусель'
        }
        
        await status.edit_text(f"⚡ Скачиваю {type_messages.get(content_type, 'контент')}...")
        
        content_info = await downloader.download_instagram_content(url, tmp_dir)
        
        if not content_info.get('files'):
            raise Exception("Не удалось скачать файлы")
        
        # Проверка расширений
        validated_files = []
        for file_path in content_info['files']:
            if os.path.exists(file_path):
                fixed_path = validate_and_fix_extension(file_path)
                validated_files.append(fixed_path)
        
        if not validated_files:
            raise Exception("Нет валидных файлов для отправки")
        
        content_info['files'] = validated_files
        
        await status.edit_text(f"📤 Отправляю {type_messages.get(content_info['type'], 'контент')}...")
        
        # Отправляем контент
        await send_content(client, message, content_info)
        
        logger.info(f"✅ Instagram {content_info['type']} отправлен ({len(validated_files)} файлов)")
        
    except Exception as e:
        raise e

async def send_content(client, message, content_info):
    """Отправка контента"""
    files = content_info['files']
    content_type = content_info['type']
    
    if not files:
        await message.reply_text("❌ Не удалось скачать контент")
        return
    
    logger.info(f"📤 Отправка {content_type}: {len(files)} файлов")
    
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
            return await asyncio.gather(*tasks, return_exceptions=True)
            
    elif content_type in ['video', 'story_video']:
        tasks = []
        for file_path in files[:10]:
            if os.path.exists(file_path):
                task = message.reply_video(
                    file_path,
                    caption=f"📹 Instagram {'история' if 'story' in content_type else 'видео'} через @azams_bot",
                    supports_streaming=True
                )
                tasks.append(task)
        
        if tasks:
            return await asyncio.gather(*tasks, return_exceptions=True)
            
    elif content_type == 'carousel':
        return await _send_carousel_fast(client, message, files)

async def _send_carousel_fast(client, message, files):
    """Отправка карусели"""
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
            return await message.reply_media_group(media_group)
        except Exception as e:
            logger.error(f"❌ Ошибка отправки медиагруппы: {e}")
            # Fallback - отправляем по одному
            tasks = []
            for file_path in files[:5]:
                if os.path.exists(file_path):
                    if file_path.lower().endswith(('.jpg', '.jpeg', '.png')):
                        tasks.append(message.reply_photo(file_path))
                    elif file_path.lower().endswith(('.mp4', '.mov', '.avi')):
                        tasks.append(message.reply_video(file_path))
            
            if tasks:
                return await asyncio.gather(*tasks, return_exceptions=True)

# ------------------------- ЗАПУСК -------------------------
if __name__ == "__main__":
    # Проверяем наличие необходимых библиотек
    try:
        import filetype
        logger.info("✅ filetype установлен")
    except ImportError:
        logger.warning("⚠️ filetype не установлен. Установите: pip install filetype")
    
    # Очистка старых сессий
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
    
    logger.info("🚀 ЗАПУСК БОТА ДЛЯ СКАЧИВАНИЯ INSTAGRAM...")
    
    try:
        app.run()
        logger.info("✅ Бот успешно запущен и готов к работе!")
    except Exception as e:
        logger.error(f"❌ Ошибка запуска бота: {e}")
