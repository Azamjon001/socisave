import os
import asyncio
import logging
import tempfile
import yt_dlp
import re
import shutil
from pyrogram import Client, filters
from pyrogram.types import InputMediaVideo
from concurrent.futures import ThreadPoolExecutor

# Конфигурация
API_ID = 26670278
API_HASH = "e3d77390fd9c22d98bb6bddca86fef1a"
BOT_TOKEN = "6788128988:AAEMmCSafiiEqtS5UWQQxfo--W0On7B6Q08"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Глобальные переменные
user_processing = {}

class InstagramVideoDownloader:
    def __init__(self):
        self.ydl_opts = {
            'outtmpl': 'downloads/%(id)s.%(ext)s',
            'format': 'bestvideo+bestaudio/best[height<=1080]/best',
            'cookiefile': 'cookies.txt',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'noplaylist': True,
            'socket_timeout': 15,
            'retries': 3,
            'fragment_retries': 3,
            'skip_unavailable_fragments': True,
            'keep_fragments': False,
            'concurrent_fragment_downloads': 6,
            'writethumbnail': False,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            }
        }
        self.thread_pool = ThreadPoolExecutor(max_workers=2)

    async def download_video(self, url: str, out_path: str):
        """Скачивание видео через yt-dlp"""
        try:
            loop = asyncio.get_event_loop()
            
            # Проверяем что это видео контент
            if not await self._is_video_content(url):
                raise Exception("Это не видео контент")
            
            result = await loop.run_in_executor(
                self.thread_pool,
                self._download_with_ytdlp,
                url, out_path
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка скачивания видео: {e}")
            raise

    async def _is_video_content(self, url: str) -> bool:
        """Проверяет является ли контент видео"""
        try:
            # Проверка по URL паттернам
            video_patterns = ['/reel/', '/reels/', '/tv/', '/video/']
            if any(pattern in url for pattern in video_patterns):
                return True
            
            # Дополнительная проверка через yt-dlp
            loop = asyncio.get_event_loop()
            ydl_opts = {'quiet': True, 'cookiefile': 'cookies.txt'}
            
            def get_info():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(url, download=False)
            
            info = await loop.run_in_executor(self.thread_pool, get_info)
            
            # Проверяем форматы на наличие видео
            if info.get('formats'):
                return any(f.get('vcodec') != 'none' for f in info['formats'])
            
            return False
            
        except Exception as e:
            logger.warning(f"Не удалось проверить тип контента: {e}")
            return any(pattern in url for pattern in ['/reel/', '/reels/', '/tv/', '/video/'])

    def _download_with_ytdlp(self, url: str, out_path: str):
        """Скачивание через yt-dlp"""
        ydl_opts = self.ydl_opts.copy()
        ydl_opts['outtmpl'] = os.path.join(out_path, '%(id)s.%(ext)s')
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            result = {
                'type': 'video',
                'files': [],
                'title': info.get('title', 'instagram_video'),
            }
            
            # Ищем скачанные файлы
            if info.get('requested_downloads'):
                for download in info['requested_downloads']:
                    file_path = download['filepath']
                    if os.path.exists(file_path) and self._is_video_file(file_path):
                        result['files'].append(file_path)
            
            if not result['files']:
                for file in os.listdir(out_path):
                    file_path = os.path.join(out_path, file)
                    if self._is_video_file(file_path):
                        result['files'].append(file_path)
            
            logger.info(f"Найдено видео файлов: {len(result['files'])}")
            return result

    def _is_video_file(self, file_path: str) -> bool:
        video_extensions = {'.mp4', '.mov', '.avi', '.webm', '.mkv'}
        file_ext = os.path.splitext(file_path)[1].lower()
        return file_ext in video_extensions and os.path.isfile(file_path)

# Создаем клиент бота
app = Client(
    "video_bot_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)

# Вспомогательные функции
def check_cookies():
    return os.path.exists("cookies.txt")

def safe_remove_directory(dir_path: str):
    try:
        if os.path.exists(dir_path):
            shutil.rmtree(dir_path)
    except:
        pass

def extract_url(text: str) -> str:
    match = re.search(r"(https?://[^\s]+)", text)
    return match.group(1) if match else ""

# Обработчики сообщений
@app.on_message(filters.command("start"))
async def start_handler(client, message):
    await message.reply_text(
        "🎥 **Video Download Bot**\n\n"
        "Отправь мне ссылку на Instagram видео (Reels, TV, Video) и я скачаю его для тебя!\n\n"
        "Поддерживаемые форматы:\n"
        "• Reels\n• Video\n• IGTV\n• Stories с видео"
    )

@app.on_message(filters.text & filters.private)
async def handle_message(client, message):
    user_id = message.from_user.id
    
    if user_id in user_processing and user_processing[user_id]:
        await message.reply_text("⏳ Уже обрабатываю ваш предыдущий запрос...")
        return
        
    user_processing[user_id] = True
    status_msg = None
    tmp_dir = None
    
    try:
        url = extract_url(message.text)
        if not url or "instagram.com" not in url:
            await message.reply_text("❌ Пожалуйста, отправьте действительную ссылку Instagram")
            return

        # Проверяем что это видео контент
        video_patterns = ['/reel/', '/reels/', '/tv/', '/video/']
        if not any(pattern in url for pattern in video_patterns):
            await message.reply_text("❌ Это не видео ссылка. Используйте @photo_bot для фото.")
            return

        if not check_cookies():
            await message.reply_text("❌ Файл cookies.txt не найден")
            return

        status_msg = await message.reply_text("⚡ Проверяю ссылку...")
        
        downloader = InstagramVideoDownloader()
        tmp_dir = tempfile.mkdtemp()
        
        await status_msg.edit_text("🎥 Скачиваю видео...")
        content_info = await downloader.download_video(url, tmp_dir)
        
        if not content_info.get('files'):
            await status_msg.edit_text("❌ Не удалось скачать видео")
            return
        
        await status_msg.edit_text("📤 Отправляю видео...")
        
        # Отправляем видео
        for file_path in content_info['files'][:1]:  # Отправляем только первое видео
            if os.path.exists(file_path):
                await message.reply_video(
                    file_path,
                    caption="🎥 Скачано через @azams_bot",
                    supports_streaming=True
                )
                break
        
        await status_msg.delete()
        await message.delete()
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        if status_msg:
            await status_msg.edit_text(f"❌ Ошибка: {str(e)}")
    finally:
        if tmp_dir:
            safe_remove_directory(tmp_dir)
        user_processing[user_id] = False

# Запуск бота
if __name__ == "__main__":
    logger.info("🚀 Запуск Video Bot...")
    if not os.path.exists("downloads"):
        os.makedirs("downloads")
    app.run()
