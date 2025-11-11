
import os
import asyncio
import logging
import tempfile
import yt_dlp
import re
import shutil
import instaloader
from pyrogram import Client, filters
from pyrogram.types import InputMediaPhoto
from concurrent.futures import ThreadPoolExecutor

# Конфигурация (одинаковые credentials)
API_ID = 26670278
API_HASH = "e3d77390fd9c22d98bb6bddca86fef1a"
BOT_TOKEN = "6788128988:AAEMmCSafiiEqtS5UWQQxfo--W0On7B6Q08"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Глобальные переменные
user_processing = {}

class InstagramPhotoDownloader:
    def __init__(self):
        self.ydl_opts = {
            'outtmpl': 'downloads/%(id)s.%(ext)s',
            'format': 'best[ext=jpg]/best[ext=png]/best',
            'cookiefile': 'cookies.txt',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'noplaylist': True,
            'socket_timeout': 15,
            'retries': 2,
            'skip_unavailable_fragments': True,
            'writethumbnail': False,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            }
        }
        self.thread_pool = ThreadPoolExecutor(max_workers=2)

    async def download_photo(self, url: str, out_path: str):
        """Скачивание фото через yt-dlp или instaloader"""
        try:
            loop = asyncio.get_event_loop()
            
            # Проверяем что это фото контент
            if not await self._is_photo_content(url):
                raise Exception("Это не фото контент")
            
            # Сначала пробуем yt-dlp
            try:
                result = await loop.run_in_executor(
                    self.thread_pool,
                    self._download_with_ytdlp,
                    url, out_path
                )
                return result
            except Exception as e:
                logger.warning(f"yt-dlp не сработал: {e}, пробуем instaloader")
                return await self._download_with_instaloader(url, out_path)
            
        except Exception as e:
            logger.error(f"Ошибка скачивания фото: {e}")
            raise

    async def _is_photo_content(self, url: str) -> bool:
        """Проверяет является ли контент фото"""
        try:
            # Исключаем видео паттерны
            video_patterns = ['/reel/', '/reels/', '/tv/', '/video/']
            if any(pattern in url for pattern in video_patterns):
                return False
            
            # Проверяем через yt-dlp
            loop = asyncio.get_event_loop()
            ydl_opts = {'quiet': True, 'cookiefile': 'cookies.txt'}
            
            def get_info():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(url, download=False)
            
            info = await loop.run_in_executor(self.thread_pool, get_info)
            
            # Если это плейлист (карусель) или нет видео - считаем фото
            if info.get('_type') == 'playlist':
                return True
                
            if info.get('formats'):
                has_video = any(f.get('vcodec') != 'none' for f in info['formats'])
                return not has_video
            
            return True
            
        except Exception as e:
            logger.warning(f"Не удалось проверить тип контента: {e}")
            # Если нет видео паттернов - считаем фото
            return not any(pattern in url for pattern in ['/reel/', '/reels/', '/tv/', '/video/'])

    def _download_with_ytdlp(self, url: str, out_path: str):
        """Скачивание через yt-dlp"""
        ydl_opts = self.ydl_opts.copy()
        ydl_opts['outtmpl'] = os.path.join(out_path, '%(id)s.%(ext)s')
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            result = {
                'type': 'photo',
                'files': [],
                'title': info.get('title', 'instagram_photo'),
            }
            
            # Ищем скачанные файлы
            if info.get('requested_downloads'):
                for download in info['requested_downloads']:
                    file_path = download['filepath']
                    if os.path.exists(file_path) and self._is_photo_file(file_path):
                        result['files'].append(file_path)
            
            if not result['files']:
                for file in os.listdir(out_path):
                    file_path = os.path.join(out_path, file)
                    if self._is_photo_file(file_path):
                        result['files'].append(file_path)
            
            # Определяем тип (одиночное фото или карусель)
            if len(result['files']) > 1:
                result['type'] = 'carousel'
            
            logger.info(f"Найдено фото файлов: {len(result['files'])}")
            return result

    async def _download_with_instaloader(self, url: str, out_path: str):
        """Скачивание через instaloader"""
        try:
            L = instaloader.Instaloader(
                dirname_pattern=out_path,
                filename_pattern='{shortcode}',
                download_pictures=True,
                download_videos=False,
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
            
            downloaded_files = []
            for file in os.listdir(out_path):
                file_path = os.path.join(out_path, file)
                if self._is_photo_file(file_path):
                    downloaded_files.append(file_path)
            
            result = {
                'type': 'carousel' if post.mediacount > 1 else 'photo',
                'files': downloaded_files,
                'title': f"instagram_{shortcode}",
            }
            
            logger.info(f"Instaloader скачал файлов: {len(downloaded_files)}")
            return result
            
        except Exception as e:
            raise Exception(f"Instaloader ошибка: {str(e)}")

    def _extract_shortcode(self, url: str):
        patterns = [
            r'instagram\.com/p/([^/?]+)',
            r'instagram\.com/stories/[^/]+/([^/?]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def _is_photo_file(self, file_path: str) -> bool:
        photo_extensions = {'.jpg', '.jpeg', '.png', '.webp'}
        file_ext = os.path.splitext(file_path)[1].lower()
        return file_ext in photo_extensions and os.path.isfile(file_path)

# Создаем клиент бота
app = Client(
    "photo_bot_session", 
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
        "🖼️ **Photo Download Bot**\n\n"
        "Отправь мне ссылку на Instagram фото или карусель и я скачаю их для тебя!\n\n"
        "Поддерживаемые форматы:\n"
        "• Фото\n• Карусели с фото\n• Stories с фото\n\n"
        "Для видео используйте @video_bot"
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

        # Проверяем что это не видео контент
        video_patterns = ['/reel/', '/reels/', '/tv/', '/video/']
        if any(pattern in url for pattern in video_patterns):
            await message.reply_text("❌ Это видео ссылка. Используйте @video_bot для видео.")
            return

        if not check_cookies():
            await message.reply_text("❌ Файл cookies.txt не найден")
            return

        status_msg = await message.reply_text("⚡ Проверяю ссылку...")
        
        downloader = InstagramPhotoDownloader()
        tmp_dir = tempfile.mkdtemp()
        
        await status_msg.edit_text("🖼️ Скачиваю фото...")
        content_info = await downloader.download_photo(url, tmp_dir)
        
        if not content_info.get('files'):
            await status_msg.edit_text("❌ Не удалось скачать фото")
            return
        
        await status_msg.edit_text("📤 Отправляю фото...")
        
        # Отправляем фото
        if content_info['type'] == 'photo' and content_info['files']:
            # Одиночное фото
            await message.reply_photo(
                content_info['files'][0],
                caption="🖼️ Скачано через @photo_bot"
            )
        else:
            # Карусель или несколько фото
            media_group = []
            for i, file_path in enumerate(content_info['files'][:10]):
                if os.path.exists(file_path):
                    media_item = InputMediaPhoto(file_path)
                    if i == 0:
                        media_item.caption = "🖼️ Скачано через @photo_bot"
                    media_group.append(media_item)
            
            if media_group:
                await message.reply_media_group(media_group)
        
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
    logger.info("🚀 Запуск Photo Bot...")
    if not os.path.exists("downloads"):
        os.makedirs("downloads")
    app.run()
