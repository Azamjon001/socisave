import os
import asyncio
import logging
import tempfile
import yt_dlp
import re
import random
import time
import requests
import shutil
from pyrogram import Client, filters
from pyrogram.errors import BadRequest, BadMsgNotification
from pyrogram.types import InputMediaPhoto, InputMediaVideo
import instaloader
import aiohttp

API_ID = 26670278
API_HASH = "e3d77390fd9c22d98bb6bddca86fef1a"
BOT_TOKEN = "6788128988:AAEMmCSafiiEqtS5UWQQxfo--W0On7B6Q08"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------------- ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ -------------------------
user_processing = {}  # Храним статус обработки для каждого пользователя
processed_messages = set()  # Отслеживаем обработанные сообщения

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

# ------------------------- ИСПРАВЛЕНО: новое имя сессии -------------------------
app = SafeClient(
    "video_bot_new_session_2024",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    sleep_threshold=15
)

# ------------------------- Instagram Downloader Class -------------------------
class InstagramDownloader:
    def __init__(self):
        pass

    async def download_instagram_content(self, url: str, out_path: str):
        """Универсальная функция для скачивания любого контента Instagram через yt-dlp"""
        try:
            # Для всего контента используем yt-dlp (быстрее чем instaloader)
            return await self._download_with_ytdlp(url, out_path)
        except Exception as e:
            logger.warning(f"yt-dlp не сработал: {e}, пробуем instaloader только для историй")
            # Для историй пробуем instaloader как запасной вариант
            if '/stories/' in url:
                return await self._download_story_with_instaloader(url, out_path)
            else:
                raise e

    async def _download_story(self, url: str, out_path: str):
        """Специальная функция для скачивания историй через yt-dlp"""
        try:
            ydl_opts = {
                'outtmpl': os.path.join(out_path, 'story_%(upload_date)s_%(id)s.%(ext)s'),
                'cookiefile': 'cookies.txt',
                'quiet': True,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                result = {
                    'type': 'story',
                    'files': [],
                    'title': f"instagram_story_{info.get('id', 'unknown')}",
                    'webpage_url': url
                }
                
                # Получаем все скачанные файлы
                if info.get('requested_downloads'):
                    for download in info['requested_downloads']:
                        if os.path.exists(download['filepath']):
                            result['files'].append(download['filepath'])
                
                # Если не нашли через requested_downloads, ищем файлы в директории
                if not result['files']:
                    for file in os.listdir(out_path):
                        if file.endswith(('.jpg', '.jpeg', '.png', '.mp4', '.mov', '.avi')):
                            result['files'].append(os.path.join(out_path, file))
                
                # Определяем тип файла
                if result['files']:
                    ext = result['files'][0].split('.')[-1].lower()
                    if ext in ['jpg', 'png', 'jpeg']:
                        result['type'] = 'story_photo'
                    elif ext in ['mp4', 'mov', 'avi']:
                        result['type'] = 'story_video'
                
                return result
                
        except Exception as e:
            logger.warning(f"yt-dlp для историй не сработал: {e}")
            raise

    async def _download_with_ytdlp(self, url: str, out_path: str):
        """Скачивание через yt-dlp для всех типов контента"""
        ydl_opts = {
            'outtmpl': os.path.join(out_path, '%(title).50s.%(ext)s'),
            'cookiefile': 'cookies.txt',
            'quiet': True,
            'nooverwrites': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            result = {
                'type': 'unknown',
                'files': [],
                'title': info.get('title', 'instagram_content'),
                'webpage_url': info.get('webpage_url', url)
            }
            
            # Получаем ВСЕ скачанные файлы
            downloaded_files = []
            
            # Способ 1: через requested_downloads (основной)
            if info.get('requested_downloads'):
                for download in info['requested_downloads']:
                    if os.path.exists(download['filepath']):
                        downloaded_files.append(download['filepath'])
            
            # Способ 2: ищем файлы в директории по шаблону
            if not downloaded_files:
                expected_filename = ydl.prepare_filename(info)
                base_name = os.path.splitext(expected_filename)[0]
                
                for file in os.listdir(out_path):
                    if file.startswith(os.path.basename(base_name)) or 'instagram' in file.lower():
                        downloaded_files.append(os.path.join(out_path, file))
            
            # Способ 3: берем все медиафайлы из директории
            if not downloaded_files:
                for file in os.listdir(out_path):
                    if file.endswith(('.jpg', '.jpeg', '.png', '.mp4', '.mov', '.avi')):
                        downloaded_files.append(os.path.join(out_path, file))
            
            result['files'] = downloaded_files
            
            # Определяем тип контента
            if not downloaded_files:
                raise Exception("Не удалось найти скачанные файлы")
            
            # Определяем по количеству файлов и расширению
            if len(downloaded_files) > 1:
                result['type'] = 'carousel'
            else:
                ext = downloaded_files[0].split('.')[-1].lower()
                if ext in ['jpg', 'png', 'jpeg']:
                    result['type'] = 'photo'
                elif ext in ['mp4', 'mov', 'avi']:
                    result['type'] = 'video'
            
            # Для историй определяем отдельно
            if '/stories/' in url:
                if result['type'] == 'photo':
                    result['type'] = 'story_photo'
                elif result['type'] == 'video':
                    result['type'] = 'story_video'
                else:
                    result['type'] = 'story'
            
            return result

    async def _download_story_with_instaloader(self, url: str, out_path: str):
        """Резервный метод для скачивания историй через instaloader"""
        try:
            L = instaloader.Instaloader(
                dirname_pattern=out_path,
                filename_pattern='{profile}_{date}',
                download_pictures=True,
                download_videos=True,
                download_geotags=False,
                download_comments=False,
                save_metadata=False,
                compress_json=False
            )
            
            username = self._extract_story_username(url)
            if not username:
                raise Exception("Не удалось извлечь username из URL истории")
            
            profile = instaloader.Profile.from_username(L.context, username)
            downloaded_files = []
            
            for story in L.get_stories([profile.userid]):
                for item in story.get_items():
                    L.download_storyitem(item, target=os.path.join(out_path, f"story_{username}"))
                    
                    for file in os.listdir(out_path):
                        if file.startswith(f"story_{username}") and not file.endswith('.txt'):
                            downloaded_files.append(os.path.join(out_path, file))
                    break
                break
            
            if not downloaded_files:
                raise Exception("Не удалось скачать истории")
            
            result = {
                'type': 'story',
                'files': downloaded_files,
                'title': f"instagram_story_{username}",
                'webpage_url': url
            }
            
            if downloaded_files:
                ext = downloaded_files[0].split('.')[-1].lower()
                if ext in ['jpg', 'png', 'jpeg']:
                    result['type'] = 'story_photo'
                elif ext in ['mp4', 'mov', 'avi']:
                    result['type'] = 'story_video'
            
            return result
            
        except Exception as e:
            raise Exception(f"Instaloader ошибка для историй: {str(e)}")

    def _extract_story_username(self, url: str):
        """Извлекает username из URL истории"""
        pattern = r'instagram\.com/stories/([^/?]+)'
        match = re.search(pattern, url)
        return match.group(1) if match else None

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
    ydl_opts = {"quiet": True, "skip_download": True, "format": "mp4[height<=720]/best[ext=mp4]/best"}
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
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)

def check_cookies_file():
    """Проверяем наличие cookies файла"""
    if not os.path.exists("cookies.txt"):
        logger.error("❌ Файл cookies.txt не найден!")
        return False
    logger.info("✅ Файл cookies.txt найден")
    return True

async def cleanup_user_message(message, delay: int = 3):
    """Удаляет сообщение пользователя после задержки"""
    try:
        await asyncio.sleep(delay)
        await message.delete()
        logger.info(f"🗑️ Удалено сообщение пользователя {message.from_user.id}")
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение: {e}")

def cleanup_old_processed_messages():
    """Очищает старые записи из processed_messages"""
    global processed_messages
    if len(processed_messages) > 1000:
        processed_messages = set(list(processed_messages)[-500:])
        logger.info("🧹 Очищены старые записи из processed_messages")

def safe_cleanup_directory(dir_path: str):
    """Безопасная очистка директории"""
    if dir_path and os.path.exists(dir_path):
        try:
            # Используем shutil для рекурсивного удаления
            shutil.rmtree(dir_path, ignore_errors=True)
            logger.info(f"✅ Директория очищена: {dir_path}")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось очистить директорию {dir_path}: {e}")

# ------------------------- ОБРАБОТЧИКИ СООБЩЕНИЙ -------------------------

@app.on_message(filters.command("start"))
async def start(client, message):
    """Обработчик команды /start"""
    logger.info(f"📩 Получена команда /start от {message.from_user.id}")
    
    message_id = f"start_{message.id}_{message.from_user.id}"
    
    if message_id in processed_messages:
        logger.info("🔄 Пропускаем дублирующее сообщение /start")
        return
        
    processed_messages.add(message_id)
    
    try:
        welcome_msg = await message.reply_text(
            "Привет! 👋\n\n"
            "📥 Отправь ссылку на Instagram — я скачаю:\n"
            "• 📹 Видео и рилсы\n" 
            "• 📸 Фото\n"
            "• 🖼️ Карусели (несколько фото/видео)\n"
            "• 📱 Истории (stories)\n\n"
            "⚡ Теперь работает БЫСТРЕЕ через yt-dlp!"
        )
        logger.info(f"✅ Отправлено приветственное сообщение пользователю {message.from_user.id}")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки приветствия: {e}")
    
    cleanup_old_processed_messages()

@app.on_message(filters.command(["help", "info"]))
async def help_command(client, message):
    """Обработчик других команд"""
    logger.info(f"📩 Получена команда help от {message.from_user.id}")
    
    message_id = f"help_{message.id}_{message.from_user.id}"
    
    if message_id in processed_messages:
        return
        
    processed_messages.add(message_id)
    
    help_text = (
        "🤖 **Помощь по боту**\n\n"
        "📥 Просто отправь ссылку на:\n"
        "• Instagram фото/видео/рилс\n"
        "• Instagram карусель (несколько фото)\n" 
        "• Instagram историю (stories)\n"
        "• YouTube видео\n\n"
        "⚡ **Новое:** фото и карусели скачиваются БЫСТРЕЕ!\n"
        "📌 Бот автоматически удалит твою ссылку после скачивания"
    )
    
    try:
        await message.reply_text(help_text)
        logger.info(f"✅ Отправлена помощь пользователю {message.from_user.id}")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки помощи: {e}")
    
    cleanup_old_processed_messages()

@app.on_message(filters.text & filters.private)
async def handle_text(client, message):
    """Обработчик текстовых сообщений от пользователей"""
    
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
            temp_msg = await message.reply_text("⏳ Ваш предыдущий запрос еще обрабатывается...")
            await asyncio.sleep(3)
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
        
        status = await message.reply_text("⏳ Определяю тип контента...")
        
        if "youtube" in url or "youtu.be" in url:
            await _handle_youtube(client, message, url, status)
        elif "instagram.com" in url:
            tmp_dir = tempfile.mkdtemp()
            await _handle_instagram(client, message, url, status, insta_downloader, tmp_dir)

        await message.delete()
        logger.info(f"✅ Обработка завершена для пользователя {user_id}")

    except Exception as e:
        logger.error(f"❌ Ошибка обработки для пользователя {user_id}: {e}")
        
        if status:
            try:
                error_msg = await message.reply_text(f"❌ Ошибка: {str(e)}")
                await asyncio.sleep(5)
                await error_msg.delete()
            except:
                pass
                
    finally:
        # Всегда очищаем временную директорию
        if tmp_dir:
            safe_cleanup_directory(tmp_dir)
            
        if status:
            try:
                await status.delete()
            except:
                pass
                
        if user_id in user_processing:
            user_processing[user_id]['processing'] = False
            
        cleanup_old_processed_messages()

async def _handle_youtube(client, message, url, status):
    """Обработка YouTube ссылок"""
    tmp_dir = None
    try:
        await status.edit_text("🔗 Получаю прямую ссылку YouTube...")
        direct_url = await asyncio.to_thread(get_youtube_direct_url, url)
        
        await status.edit_text("📤 Отправляю видео...")
        await message.reply_video(
            direct_url, 
            caption="📥 YouTube видео скачано через @azams_bot"
        )
        logger.info("✅ YouTube видео отправлено через прямую ссылку")
        
    except Exception as e:
        logger.warning(f"❌ Прямая ссылка YouTube не сработала: {e}, скачиваю файл...")
        await status.edit_text("📥 Скачиваю видео...")
        tmp_dir = tempfile.mkdtemp()
        
        try:
            file_path = await asyncio.to_thread(download_youtube_video, url, tmp_dir)
            await status.edit_text("📤 Отправляю видео...")
            await message.reply_video(
                file_path, 
                caption="📥 YouTube видео скачано через @azams_bot"
            )
            logger.info("✅ YouTube видео отправлено как файл")
            
        except Exception as download_error:
            raise download_error
            
    finally:
        if tmp_dir:
            safe_cleanup_directory(tmp_dir)

async def _handle_instagram(client, message, url, status, downloader, tmp_dir):
    """Обработка Instagram ссылок"""
    if not check_cookies_file():
        await status.edit_text("❌ Файл cookies.txt не найден. Instagram недоступен.")
        await asyncio.sleep(5)
        return
        
    try:
        await status.edit_text("📥 Скачиваю контент из Instagram...")
        
        # Скачиваем контент
        content_info = await downloader.download_instagram_content(url, tmp_dir)
        
        if not content_info.get('files'):
            raise Exception("Не удалось скачать файлы")
        
        await status.edit_text(f"📤 Отправляю {content_info['type']}...")
        
        # Отправляем в зависимости от типа контента
        if content_info['type'] in ['photo', 'story_photo']:
            for file_path in content_info['files']:
                await message.reply_photo(
                    file_path,
                    caption=f"📸 Instagram {'история' if 'story' in content_info['type'] else 'фото'} через @azams_bot"
                )
            
        elif content_info['type'] in ['video', 'story_video']:
            for file_path in content_info['files']:
                await message.reply_video(
                    file_path,
                    caption=f"📹 Instagram {'история' if 'story' in content_info['type'] else 'видео'} через @azams_bot"
                )
            
        elif content_info['type'] == 'carousel':
            await _send_carousel(client, message, content_info['files'])
            
        elif content_info['type'] == 'story':
            for file_path in content_info['files']:
                if file_path.lower().endswith(('.jpg', '.jpeg', '.png')):
                    await message.reply_photo(
                        file_path,
                        caption="📸 Instagram история через @azams_bot"
                    )
                elif file_path.lower().endswith(('.mp4', '.mov', '.avi')):
                    await message.reply_video(
                        file_path,
                        caption="📹 Instagram история через @azams_bot"
                    )
        
        logger.info(f"✅ Instagram {content_info['type']} отправлен")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при обработке Instagram: {e}")
        raise e

async def _send_carousel(client, message, files):
    """Отправка карусели (нескольких медиафайлов)"""
    media_group = []
    
    for i, file_path in enumerate(files):
        if i >= 10:
            break
            
        if file_path.lower().endswith(('.jpg', '.jpeg', '.png')):
            if i == 0:
                media_group.append(InputMediaPhoto(file_path, caption="🖼️ Instagram карусель через @azams_bot"))
            else:
                media_group.append(InputMediaPhoto(file_path))
                
        elif file_path.lower().endswith(('.mp4', '.mov', '.avi')):
            if i == 0:
                media_group.append(InputMediaVideo(file_path, caption="🎬 Instagram карусель через @azams_bot"))
            else:
                media_group.append(InputMediaVideo(file_path))
    
    if media_group:
        await message.reply_media_group(media_group)

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
    
    logger.info("🚀 Запуск бота...")
    logger.info("⚡ Бот теперь работает БЫСТРЕЕ через yt-dlp для фото и каруселей!")
    
    try:
        app.run()
        logger.info("✅ Бот успешно запущен и готов к работе!")
    except Exception as e:
        logger.error(f"❌ Ошибка запуска бота: {e}")
