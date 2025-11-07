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
from pyrogram.types import InputMediaPhoto, InputMediaVideo, InlineKeyboardButton, InlineKeyboardMarkup
import instaloader
import aiohttp
import shutil
from concurrent.futures import ThreadPoolExecutor
from pydub import AudioSegment

API_ID = 26670278
API_HASH = "e3d77390fd9c22d98bb6bddca86fef1a"
BOT_TOKEN = "6788128988:AAEMmCSafiiEqtS5UWQQxfo--W0On7B6Q08"

# Настройки AudD API
AUDD_API_TOKEN = "YOUR_AUDD_API_TOKEN"  # Замени на свой токен от audd.io

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------------- ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ -------------------------
user_processing = {}
processed_messages = set()

# ------------------------- КЛАСС ДЛЯ РАСПОЗНАВАНИЯ МУЗЫКИ ЧЕРЕЗ AUDD -------------------------
class MusicRecognizer:
    def __init__(self, api_token):
        self.api_token = api_token
    
    def extract_audio_from_video(self, video_path, output_audio_path=None):
        """Извлекает аудио из видео файла"""
        try:
            if output_audio_path is None:
                output_audio_path = video_path.replace('.mp4', '_audio.mp3')
            
            # Используем pydub для извлечения аудио
            audio = AudioSegment.from_file(video_path)
            
            # Обрезаем аудио до 30 секунд для экономии API запросов
            audio_duration = len(audio)
            if audio_duration > 30000:  # Если больше 30 секунд
                audio = audio[:30000]  # Берем первые 30 секунд
                logger.info("✂️ Аудио обрезано до 30 секунд")
            
            audio.export(output_audio_path, format="mp3", bitrate="128k")
            
            logger.info(f"✅ Аудио извлечено: {output_audio_path}")
            return output_audio_path
            
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения аудио: {e}")
            raise Exception(f"Не удалось извлечь аудио из видео: {str(e)}")
    
    def recognize_music(self, audio_path):
        """Распознает музыку через AudD API"""
        try:
            with open(audio_path, 'rb') as audio_file:
                files = {
                    'file': audio_file
                }
                data = {
                    'api_token': self.api_token,
                    'return': 'spotify,apple_music,deezer'
                }
                
                # Отправляем запрос к AudD API
                response = requests.post(
                    "https://api.audd.io/",
                    files=files,
                    data=data,
                    timeout=30
                )
                
                if response.status_code != 200:
                    raise Exception(f"API вернул статус {response.status_code}")
                
                result = response.json()
                return self._parse_audd_result(result)
                
        except Exception as e:
            logger.error(f"❌ Ошибка распознавания музыки: {e}")
            return None
    
    def _parse_audd_result(self, result):
        """Парсит результат от AudD"""
        try:
            if result['status'] == 'success' and result['result']:
                track_info = result['result']
                
                # Извлекаем информацию о треке
                parsed_info = {
                    'title': track_info.get('title', 'Неизвестно'),
                    'artist': track_info.get('artist', 'Неизвестный артист'),
                    'album': track_info.get('album', 'Неизвестный альбом'),
                    'release_date': track_info.get('release_date', 'Неизвестно'),
                    'label': track_info.get('label', 'Неизвестно'),
                    'confidence': track_info.get('score', 0) * 100
                }
                
                # Добавляем ссылки на музыкальные платформы
                platforms = {}
                
                # Spotify
                if 'spotify' in track_info:
                    spotify_data = track_info['spotify']
                    if 'external_urls' in spotify_data and 'spotify' in spotify_data['external_urls']:
                        platforms['spotify'] = spotify_data['external_urls']['spotify']
                
                # Apple Music
                if 'apple_music' in track_info:
                    apple_data = track_info['apple_music']
                    if 'url' in apple_data:
                        platforms['apple_music'] = apple_data['url']
                
                # Deezer
                if 'deezer' in track_info:
                    deezer_data = track_info['deezer']
                    if 'link' in deezer_data:
                        platforms['deezer'] = deezer_data['link']
                
                parsed_info['platforms'] = platforms
                return parsed_info
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга результата AudD: {e}")
            return None
    
    def get_music_platform_links(self, track_info):
        """Генерирует ссылки на музыкальные платформы"""
        title = track_info['title']
        artist = track_info['artist']
        
        search_query = f"{artist} {title}".replace(' ', '+')
        
        platforms = {
            'youtube': f"https://www.youtube.com/results?search_query={search_query}",
            'youtube_music': f"https://music.youtube.com/search?q={search_query}",
            'spotify': f"https://open.spotify.com/search/{search_query}",
            'apple_music': f"https://music.apple.com/search?term={search_query}",
            'deezer': f"https://www.deezer.com/search/{search_query}",
            'soundcloud': f"https://soundcloud.com/search?q={search_query}"
        }
        
        # Добавляем прямые ссылки если есть из API
        if 'platforms' in track_info:
            if 'spotify' in track_info['platforms']:
                platforms['spotify_direct'] = track_info['platforms']['spotify']
            if 'apple_music' in track_info['platforms']:
                platforms['apple_music_direct'] = track_info['platforms']['apple_music']
            if 'deezer' in track_info['platforms']:
                platforms['deezer_direct'] = track_info['platforms']['deezer']
        
        return platforms

# Инициализируем распознаватель музыки
music_recognizer = MusicRecognizer(AUDD_API_TOKEN)

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

# ------------------------- ОПТИМИЗИРОВАННЫЙ Instagram Downloader -------------------------
class InstagramDownloader:
    def __init__(self):
        self.fast_ydl_opts = {
            'outtmpl': 'downloads/%(id)s.%(ext)s',
            'format': 'best[height<=720]',
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
        """ОПТИМИЗИРОВАННАЯ функция для скачивания"""
        try:
            loop = asyncio.get_event_loop()
            content_type = self._determine_content_type(url)
            logger.info(f"🔍 Определен тип контента: {content_type}")
            
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
            return result
        except Exception as e:
            logger.warning(f"Быстрый метод не сработал: {e}, пробуем instaloader")
            return await self._download_with_instaloader(url, out_path)

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

    def _download_story_fast(self, url: str, out_path: str, content_type: str):
        """ОПТИМИЗИРОВАННОЕ скачивание историй"""
        try:
            ydl_opts = self.fast_ydl_opts.copy()
            ydl_opts['outtmpl'] = os.path.join(out_path, 'story_%(id)s.%(ext)s')
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                result = {
                    'type': 'story',
                    'files': [],
                    'title': f"instagram_story_{info.get('id', 'unknown')}",
                    'webpage_url': url
                }
                
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
                
                if result['files']:
                    ext = result['files'][0].split('.')[-1].lower()
                    if ext in ['mp4', 'mov', 'avi']:
                        result['type'] = 'story_video'
                    else:
                        result['type'] = 'story_photo'
                
                return result
                
        except Exception as e:
            logger.warning(f"Быстрый yt-dlp для историй не сработал: {e}")
            raise

    def _download_with_ytdlp_fast(self, url: str, out_path: str, content_type: str):
        """ОПТИМИЗИРОВАННОЕ скачивание через yt-dlp"""
        ydl_opts = self.fast_ydl_opts.copy()
        ydl_opts['outtmpl'] = os.path.join(out_path, '%(id)s.%(ext)s')
        
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

    def _is_media_file_fast(self, file_path: str) -> bool:
        """БЫСТРАЯ проверка медиафайла"""
        media_extensions = {'.jpg', '.jpeg', '.png', '.mp4', '.mov', '.avi', '.webm'}
        file_ext = os.path.splitext(file_path)[1].lower()
        return file_ext in media_extensions and os.path.isfile(file_path)

    async def _download_with_instaloader(self, url: str, out_path: str):
        """Ваш оригинальный метод для fallback"""
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
                if ext in ['mp4', 'mov', 'avi']:
                    result['type'] = 'video'
                    
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
            "⚡ **БЫСТРЫЙ Instagram Downloader** ⚡\n\n"
            "📥 Отправь ссылку на Instagram — я скачаю МГНОВЕННО:\n"
            "• 📹 Видео и рилсы\n" 
            "• 📸 Фото\n"
            "• 🖼️ Карусели\n"
            "• 📱 Истории\n\n"
            "🎵 **НОВАЯ ФУНКЦИЯ:** Распознавание музыки в видео!\n"
            "🚀 Оптимизировано для максимальной скорости!"
        )
        logger.info(f"✅ Отправлено приветственное сообщение пользователю {message.from_user.id}")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки приветствия: {e}")
    
    cleanup_old_processed_messages()

@app.on_message(filters.command(["shazam", "music", "recognize"]))
async def shazam_command(client, message):
    """Команда для ручного запуска распознавания музыки"""
    logger.info(f"🎵 Получена команда Shazam от {message.from_user.id}")
    
    if message.reply_to_message and message.reply_to_message.video:
        await handle_shazam_request(message.reply_to_message, manual=True)
    else:
        await message.reply_text(
            "🎵 **Распознавание музыки**\n\n"
            "Чтобы распознать музыку:\n"
            "1. Отправь видео с музыкой\n"
            "2. Или ответь командой /shazam на видео\n\n"
            "Или просто отправь ссылку на Instagram видео - "
            "я автоматически предложу распознать музыку!"
        )

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
    """ОПТИМИЗИРОВАННАЯ обработка Instagram с функцией Shazam"""
    if not check_cookies_file():
        await status.edit_text("❌ Файл cookies.txt не найден. Instagram недоступен.")
        await asyncio.sleep(3)
        return
        
    try:
        await status.edit_text("⚡ Скачиваю контент...")
        
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
        
        await status.edit_text(f"📤 Отправляю {content_info['type']}...")
        
        # Отправляем контент и добавляем кнопку Shazam для видео
        await send_content_with_shazam(client, message, content_info)
        
        logger.info(f"✅ Instagram {content_info['type']} отправлен ({len(validated_files)} файлов)")
        
    except Exception as e:
        raise e

async def send_content_with_shazam(client, message, content_info):
    """Отправка контента с кнопкой Shazam для видео"""
    files = content_info['files']
    content_type = content_info['type']
    
    # Создаем клавиатуру с кнопкой Shazam для видео
    keyboard = None
    if content_type in ['video', 'story_video']:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎵 Распознать музыку", callback_data=f"shazam_{message.id}")]
        ])
    
    if content_type in ['photo', 'story_photo']:
        tasks = []
        for file_path in files[:10]:
            if os.path.exists(file_path):
                task = message.reply_photo(
                    file_path,
                    caption=f"📸 Instagram {'история' if 'story' in content_type else 'фото'} через @azams_bot",
                    reply_markup=keyboard
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
                    caption=f"📹 Instagram {'история' if 'story' in content_type else 'видео'} через @azams_bot\n\n🎵 Нажми кнопку ниже чтобы распознать музыку!",
                    reply_markup=keyboard,
                    supports_streaming=True
                )
                tasks.append(task)
        
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            # Сохраняем информацию о видео для последующего распознавания
            for result in results:
                if hasattr(result, 'id'):
                    user_processing[message.from_user.id] = {
                        'video_files': files,
                        'processing': False
                    }
            return results
            
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
            # Fallback
            tasks = []
            for file_path in files[:5]:
                if os.path.exists(file_path):
                    if file_path.lower().endswith(('.jpg', '.jpeg', '.png')):
                        tasks.append(message.reply_photo(file_path))
                    elif file_path.lower().endswith(('.mp4', '.mov', '.avi')):
                        tasks.append(message.reply_video(file_path))
            
            if tasks:
                return await asyncio.gather(*tasks, return_exceptions=True)

@app.on_callback_query(filters.regex(r"^shazam_"))
async def handle_shazam_callback(client, callback_query):
    """Обработка нажатия на кнопку Shazam"""
    user_id = callback_query.from_user.id
    message_id = callback_query.message.id
    
    logger.info(f"🎵 Нажата кнопка Shazam пользователем {user_id}")
    
    await callback_query.answer("🔍 Распознаю музыку...")
    
    # Ищем видео файлы пользователя
    if user_id not in user_processing or 'video_files' not in user_processing[user_id]:
        await callback_query.message.reply_text("❌ Не удалось найти видео для распознавания. Попробуйте отправить видео заново.")
        return
    
    video_files = user_processing[user_id]['video_files']
    
    if not video_files:
        await callback_query.message.reply_text("❌ Видео файлы не найдены.")
        return
    
    # Используем первое видео для распознавания
    video_path = video_files[0]
    
    if not os.path.exists(video_path):
        await callback_query.message.reply_text("❌ Видео файл не найден на сервере.")
        return
    
    await handle_shazam_request(callback_query.message, video_path)

async def handle_shazam_request(message, video_path=None, manual=False):
    """Обработка запроса на распознавание музыки"""
    status_msg = await message.reply_text("🎵 Извлекаю аудио из видео...")
    
    try:
        # Создаем временную директорию для аудио
        audio_tmp_dir = tempfile.mkdtemp()
        audio_path = os.path.join(audio_tmp_dir, "extracted_audio.mp3")
        
        # Извлекаем аудио
        await status_msg.edit_text("🔊 Извлекаю аудио дорожку...")
        extracted_audio_path = music_recognizer.extract_audio_from_video(video_path, audio_path)
        
        if not os.path.exists(extracted_audio_path):
            raise Exception("Не удалось извлечь аудио из видео")
        
        # Распознаем музыку
        await status_msg.edit_text("🔍 Отправляю аудио на распознавание...")
        music_info = music_recognizer.recognize_music(extracted_audio_path)
        
        if not music_info:
            await status_msg.edit_text("❌ Не удалось распознать музыку в этом видео.\n\nВозможные причины:\n• Слишком короткий аудио фрагмент\n• Фоновая музыка слишком тихая\n• Трек не найден в базе данных")
            return
        
        # Получаем ссылки на платформы
        platform_links = music_recognizer.get_music_platform_links(music_info)
        
        # Формируем сообщение с результатом
        result_text = (
            f"🎵 **Музыка распознана!** 🎵\n\n"
            f"**Трек:** {music_info['title']}\n"
            f"**Артист:** {music_info['artist']}\n"
            f"**Альбом:** {music_info['album']}\n"
            f"**Точность:** {music_info['confidence']:.1f}%\n\n"
            f"**Слушать на:**"
        )
        
        # Создаем кнопки для музыкальных платформ
        buttons = []
        row = []
        
        platforms_to_show = {
            'YouTube': platform_links.get('youtube'),
            'YouTube Music': platform_links.get('youtube_music'),
            'Spotify': platform_links.get('spotify_direct') or platform_links.get('spotify'),
            'Apple Music': platform_links.get('apple_music_direct') or platform_links.get('apple_music'),
            'Deezer': platform_links.get('deezer_direct') or platform_links.get('deezer'),
            'SoundCloud': platform_links.get('soundcloud')
        }
        
        for platform_name, platform_url in platforms_to_show.items():
            if platform_url:
                row.append(InlineKeyboardButton(platform_name, url=platform_url))
                if len(row) == 2:  # По 2 кнопки в ряду
                    buttons.append(row)
                    row = []
        
        if row:  # Добавляем оставшиеся кнопки
            buttons.append(row)
        
        # Добавляем кнопку для повторного распознавания
        buttons.append([InlineKeyboardButton("🔄 Распознать еще раз", callback_data="shazam_retry")])
        
        keyboard = InlineKeyboardMarkup(buttons)
        
        await status_msg.edit_text(result_text, reply_markup=keyboard)
        logger.info(f"✅ Музыка распознана: {music_info['artist']} - {music_info['title']}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка распознавания музыки: {e}")
        await status_msg.edit_text(f"❌ Ошибка распознавания музыки: {str(e)}")
    
    finally:
        # Очистка временных файлов
        if 'audio_tmp_dir' in locals() and os.path.exists(audio_tmp_dir):
            safe_remove_directory(audio_tmp_dir)

@app.on_callback_query(filters.regex(r"^shazam_retry$"))
async def handle_shazam_retry(client, callback_query):
    """Обработка повторного распознавания"""
    await callback_query.answer("🔄 Запускаю повторное распознавание...")
    await handle_shazam_request(callback_query.message)

# ------------------------- ЗАПУСК -------------------------
if __name__ == "__main__":
    # Проверяем наличие необходимых библиотек
    try:
        import pydub
        logger.info("✅ pydub установлен")
    except ImportError:
        logger.error("❌ pydub не установлен. Установите: pip install pydub")
    
    try:
        import filetype
        logger.info("✅ filetype установлен")
    except ImportError:
        logger.warning("⚠️ filetype не установлен. Установите: pip install filetype")
    
    # Проверяем настройки AudD
    if AUDD_API_TOKEN == "YOUR_AUDD_API_TOKEN":
        logger.warning("⚠️ AudD API не настроен! Функция распознавания музыки недоступна.")
        logger.info("ℹ️ Получите токен на https://audd.io/ и замените в коде")
    else:
        logger.info("✅ AudD API настроен - функция распознавания музыки доступна!")
    
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
    
    logger.info("🚀 ЗАПУСК БОТА С ФУНКЦИЕЙ SHAZAM...")
    logger.info("🎵 РАСПОЗНАВАНИЕ МУЗЫКИ АКТИВИРОВАНО!")
    
    try:
        app.run()
        logger.info("✅ Бот успешно запущен и готов к работе!")
    except Exception as e:
        logger.error(f"❌ Ошибка запуска бота: {e}")
