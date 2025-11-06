import os
import asyncio
import logging
import tempfile
import yt_dlp
import re
import time
from pyrogram import Client, filters
from pyrogram.errors import BadRequest, BadMsgNotification
from pyrogram.types import InputMediaPhoto, InputMediaVideo
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

# ------------------------- УЛУЧШЕННЫЙ Instagram Downloader -------------------------
class InstagramDownloader:
    def __init__(self):
        self.instagram_ydl_opts = {
            'outtmpl': 'downloads/%(id)s.%(ext)s',
            'format': 'best',
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
        
        self.thread_pool = ThreadPoolExecutor(max_workers=3)

    async def download_instagram_content(self, url: str, out_path: str):
        """УНИВЕРСАЛЬНАЯ функция для скачивания ВСЕГО контента из Instagram"""
        try:
            # Используем yt-dlp для получения информации о контенте
            loop = asyncio.get_event_loop()
            content_info = await loop.run_in_executor(
                self.thread_pool,
                self._get_content_info_with_ytdlp,
                url
            )
            
            logger.info(f"🔍 Определен тип контента: {content_info['type']}")
            
            # Скачиваем контент
            result = await loop.run_in_executor(
                self.thread_pool,
                self._download_all_content,
                url, out_path, content_info
            )
            
            return result
            
        except Exception as e:
            logger.warning(f"yt-dlp не сработал: {e}, пробуем instaloader")
            return await self._download_with_instaloader(url, out_path)

    def _get_content_info_with_ytdlp(self, url: str):
        """Получает информацию о контенте через yt-dlp"""
        ydl_opts = self.instagram_ydl_opts.copy()
        ydl_opts['skip_download'] = True
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            content_type = 'unknown'
            is_video = False
            is_photo = False
            is_carousel = False
            
            # Определяем тип контента
            if info.get('_type') == 'playlist':
                is_carousel = True
            elif info.get('entries'):
                is_carousel = True
            else:
                # Проверяем расширение
                if info.get('ext'):
                    ext = info['ext'].lower()
                    if ext in ['mp4', 'mov', 'avi', 'webm']:
                        is_video = True
                    elif ext in ['jpg', 'jpeg', 'png']:
                        is_photo = True
            
            # Дополнительные проверки
            if info.get('duration') and info['duration'] > 0:
                is_video = True
            elif info.get('width') and info.get('height'):
                # Если есть размеры, но нет длительности - вероятно фото
                is_photo = True
            
            # Финальное определение типа
            if is_carousel:
                content_type = 'carousel'
            elif is_video:
                content_type = 'video'
            elif is_photo:
                content_type = 'photo'
            else:
                content_type = 'mixed'
            
            return {
                'type': content_type,
                'info': info,
                'url': url
            }

    def _download_all_content(self, url: str, out_path: str, content_info: dict):
        """Скачивает ВЕСЬ контент независимо от типа"""
        ydl_opts = self.instagram_ydl_opts.copy()
        ydl_opts['outtmpl'] = os.path.join(out_path, '%(id)s_%(playlist_index)s.%(ext)s')
        
        # Скачиваем все доступные форматы
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            result = {
                'type': content_info['type'],
                'files': [],
                'title': info.get('title', 'instagram_content'),
                'webpage_url': info.get('webpage_url', url),
                'original_info': content_info
            }
            
            # Собираем ВСЕ скачанные файлы
            downloaded_files = []
            
            # Ищем в requested_downloads
            if info.get('requested_downloads'):
                for download in info['requested_downloads']:
                    file_path = download['filepath']
                    if os.path.exists(file_path) and self._is_media_file(file_path):
                        downloaded_files.append(file_path)
            
            # Ищем в директории
            if not downloaded_files:
                for file in os.listdir(out_path):
                    file_path = os.path.join(out_path, file)
                    if self._is_media_file(file_path):
                        downloaded_files.append(file_path)
            
            result['files'] = downloaded_files
            
            # Уточняем тип на основе скачанных файлов
            if downloaded_files:
                video_files = [f for f in downloaded_files if f.lower().endswith(('.mp4', '.mov', '.avi', '.webm'))]
                photo_files = [f for f in downloaded_files if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
                
                if video_files and photo_files:
                    result['type'] = 'mixed'
                elif video_files:
                    result['type'] = 'video'
                elif photo_files:
                    result['type'] = 'photo'
                
                result['video_files'] = video_files
                result['photo_files'] = photo_files
            
            return result

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
            video_files = []
            photo_files = []
            
            for file in os.listdir(out_path):
                file_path = os.path.join(out_path, file)
                if self._is_media_file(file_path):
                    downloaded_files.append(file_path)
                    if file_path.lower().endswith(('.mp4', '.mov', '.avi', '.webm')):
                        video_files.append(file_path)
                    elif file_path.lower().endswith(('.jpg', '.jpeg', '.png')):
                        photo_files.append(file_path)
            
            # Определяем тип
            if video_files and photo_files:
                content_type = 'mixed'
            elif video_files:
                content_type = 'video'
            elif photo_files:
                content_type = 'photo'
            else:
                content_type = 'unknown'
            
            return {
                'type': content_type,
                'files': downloaded_files,
                'video_files': video_files,
                'photo_files': photo_files,
                'title': f"instagram_{shortcode}",
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
    if not os.path.exists("cookies.txt"):
        logger.error("❌ Файл cookies.txt не найден!")
        return False
    logger.info("✅ Файл cookies.txt найден")
    return True

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

# ------------------------- ОБРАБОТЧИКИ СООБЩЕНИЙ -------------------------

@app.on_message(filters.command("start"))
async def start(client, message):
    logger.info(f"📩 Получена команда /start от {message.from_user.id}")
    
    message_id = f"start_{message.id}_{message.from_user.id}"
    
    if message_id in processed_messages:
        return
        
    processed_messages.add(message_id)
    
    try:
        await message.reply_text(
            "⚡ **ULTRA FAST Instagram Downloader** ⚡\n\n"
            "📥 Отправь ссылку на Instagram:\n"
            "• Фото, видео, рилсы\n"
            "• Карусели, истории\n\n"
            "🚀 Скачиваю ВЕСЬ контент из поста!"
        )
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
        "• Instagram фото/видео/рилс/карусели\n\n"
        "⚡ **СКАЧИВАЮ ВЕСЬ КОНТЕНТ!**\n"
        "📌 Если в посте есть и фото и видео - пришлю и то и другое"
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
        return
    
    user_id = message.from_user.id
    text = message.text.strip()
    
    url = extract_first_url(text)
    logger.info(f"🔍 Извлечен URL: {url}")
    
    # ТОЛЬКО INSTAGRAM
    if not url or "instagram.com" not in url:
        logger.info("❌ URL не найден или не поддерживается (только Instagram)")
        try:
            temp_msg = await message.reply_text("❌ Поддерживаются только ссылки Instagram")
            await asyncio.sleep(3)
            await temp_msg.delete()
        except:
            pass
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
    
    tmp_dir = None
    
    try:
        logger.info(f"🔄 Обработка Instagram URL: {url}")
        
        # Сразу начинаем скачивание без лишних сообщений
        tmp_dir = tempfile.mkdtemp()
        downloader = InstagramDownloader()
        
        if not check_cookies_file():
            raise Exception("Файл cookies.txt не найден")
        
        # Скачиваем ВЕСЬ контент
        content_info = await downloader.download_instagram_content(url, tmp_dir)
        
        if not content_info.get('files'):
            raise Exception("Не удалось скачать файлы")
        
        logger.info(f"✅ Скачано файлов: {len(content_info['files'])}")
        logger.info(f"📊 Тип контента: {content_info['type']}")
        logger.info(f"🎥 Видео: {len(content_info.get('video_files', []))}")
        logger.info(f"🖼️ Фото: {len(content_info.get('photo_files', []))}")
        
        # Отправляем ВЕСЬ контент
        await send_all_content(client, message, content_info)
        
        logger.info(f"✅ Контент отправлен пользователю {user_id}")

    except Exception as e:
        logger.error(f"❌ Ошибка обработки для пользователя {user_id}: {e}")
        try:
            error_msg = await message.reply_text(f"❌ Ошибка: {str(e)}")
            await asyncio.sleep(4)
            await error_msg.delete()
        except:
            pass
                
    finally:
        if tmp_dir and os.path.exists(tmp_dir):
            safe_remove_directory(tmp_dir)
                
        if user_id in user_processing:
            user_processing[user_id]['processing'] = False
            
        cleanup_old_processed_messages()

async def send_all_content(client, message, content_info):
    """Отправляет ВЕСЬ скачанный контент"""
    files = content_info.get('files', [])
    video_files = content_info.get('video_files', [])
    photo_files = content_info.get('photo_files', [])
    
    logger.info(f"📤 Отправка: {len(video_files)} видео, {len(photo_files)} фото")
    
    sent_count = 0
    
    # Сначала отправляем видео
    for video_path in video_files[:5]:  # Ограничиваем количество
        if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
            try:
                await message.reply_video(
                    video_path,
                    caption=""
                )
                sent_count += 1
                await asyncio.sleep(1)  # Задержка между отправками
            except Exception as e:
                logger.warning(f"⚠️ Не удалось отправить видео {video_path}: {e}")
    
    # Затем отправляем фото
    for photo_path in photo_files[:10]:  # Ограничиваем количество
        if os.path.exists(photo_path) and os.path.getsize(photo_path) > 0:
            try:
                await message.reply_photo(
                    photo_path,
                    caption=""
                )
                sent_count += 1
                await asyncio.sleep(0.5)  # Меньшая задержка для фото
            except Exception as e:
                logger.warning(f"⚠️ Не удалось отправить фото {photo_path}: {e}")
    
    # Если ничего не отправилось, пробуем отправить как есть
    if sent_count == 0 and files:
        for file_path in files[:3]:
            if os.path.exists(file_path):
                try:
                    if file_path.lower().endswith(('.mp4', '.mov', '.avi', '.webm')):
                        await message.reply_video(file_path)
                    else:
                        await message.reply_photo(file_path)
                    sent_count += 1
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось отправить файл {file_path}: {e}")
    
    # Финальное сообщение с результатом
    if sent_count > 0:
        result_text = f"✅ Скачано и отправлено: {sent_count} файлов"
        if video_files:
            result_text += f"\n🎥 Видео: {len(video_files)}"
        if photo_files:
            result_text += f"\n🖼️ Фото: {len(photo_files)}"
        
        await message.reply_text(result_text)
    else:
        await message.reply_text("❌ Не удалось отправить скачанные файлы")

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
    
    # Проверка cookies
    if os.path.exists("cookies.txt"):
        logger.info("✅ Файл cookies.txt найден - Instagram доступен")
    else:
        logger.warning("⚠️ Файл cookies.txt не найден - Instagram недоступен")
    
    # Создание директорий
    if not os.path.exists("downloads"):
        os.makedirs("downloads")
    
    logger.info("🚀 ЗАПУСК УЛУЧШЕННОГО БОТА...")
    logger.info("🔧 Бот скачивает ВЕСЬ контент из Instagram постов")
    
    try:
        app.run()
        logger.info("✅ Бот успешно запущен и готов к работе!")
    except Exception as e:
        logger.error(f"❌ Ошибка запуска бота: {e}")
