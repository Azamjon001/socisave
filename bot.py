import os
import asyncio
import logging
import tempfile
import yt_dlp
import re
from pyrogram import Client, filters
from pyrogram.types import InputMediaPhoto, InputMediaVideo
import shutil
from concurrent.futures import ThreadPoolExecutor

API_ID = 26670278
API_HASH = "e3d77390fd9c22d98bb6bddca86fef1a"
BOT_TOKEN = "6788128988:AAEMmCSafiiEqtS5UWQQxfo--W0On7B6Q08"

logging.basicConfig(level=logging.WARNING)  # УМЕНЬШИЛИ ЛОГГИРОВАНИЕ
logger = logging.getLogger(__name__)

# ------------------------- УПРОЩЕННЫЕ ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ -------------------------
user_processing = {}

# ------------------------- СУПЕР-БЫСТРЫЙ КЛИЕНТ -------------------------
app = Client(
    "ultra_fast_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=150,  # ЕЩЕ БОЛЬШЕ WORKERS
    sleep_threshold=120,  # МИНИМУМ "ЗАСЫПАНИЙ"
    max_concurrent_transmissions=15,  # МАКСИМАЛЬНАЯ ПАРАЛЛЕЛЬНАЯ ОТПРАВКА
)

# ------------------------- УЛЬТРА-БЫСТРЫЙ Instagram Downloader -------------------------
class UltraFastInstagramDownloader:
    def __init__(self):
        # СУПЕР-ОПТИМИЗИРОВАННЫЕ НАСТРОЙКИ
        self.ultra_fast_ydl_opts = {
            'outtmpl': 'dl/%(id)s.%(ext)s',  # КОРОТКИЕ ИМЕНА
            'format': 'best[height<=480]/best[height<=720]',  # СНАЧАЛА НИЗКОЕ КАЧЕСТВО
            'cookiefile': 'cookies.txt',
            'quiet': True,
            'no_warnings': True,
            
            # ⚡⚡⚡ АГРЕССИВНЫЕ ОПТИМИЗАЦИИ ⚡⚡⚡
            'socket_timeout': 8,           # ОЧЕНЬ КОРОТКИЕ ТАЙМАУТЫ
            'extractretry': 0,             # БЕЗ ПОВТОРНЫХ ПОПЫТОК
            'retries': 1,                  # МИНИМУМ ПОВТОРОВ
            'fragment_retries': 1,
            'skip_unavailable_fragments': True,
            'keep_fragments': False,
            'concurrent_fragment_downloads': 10,  # МАКСИМАЛЬНАЯ ПАРАЛЛЕЛЬНОСТЬ
            'noprogress': True,            # БЕЗ ИНДИКАТОРА ПРОГРЕССА
            'nopart': True,                # БЕЗ ЧАСТИЧНЫХ ФАЙЛОВ
            
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15',  # MOBILE USER-AGENT
                'Accept': '*/*',
                'Accept-Encoding': 'gzip, deflate, br',
            }
        }
        
        self.thread_pool = ThreadPoolExecutor(max_workers=5)  # БОЛЬШЕ ПОТОКОВ

    async def download_instagram_content(self, url: str, out_path: str):
        """УЛЬТРА-БЫСТРАЯ функция скачивания"""
        loop = asyncio.get_event_loop()
        
        # ПРОБУЕМ САМЫЙ БЫСТРЫЙ МЕТОД СРАЗУ
        try:
            result = await loop.run_in_executor(
                self.thread_pool, 
                self._download_ultra_fast, 
                url, out_path
            )
            return result
        except Exception as e:
            # ЕСЛИ НЕ СРАБОТАЛО - ПРОБУЕМ БЕЗ COOKIES
            try:
                result = await loop.run_in_executor(
                    self.thread_pool,
                    self._download_no_cookies,
                    url, out_path
                )
                return result
            except Exception:
                raise Exception(f"Не удалось скачать: {str(e)[:50]}")

    def _download_ultra_fast(self, url: str, out_path: str):
        """САМЫЙ БЫСТРЫЙ МЕТОД"""
        ydl_opts = self.ultra_fast_ydl_opts.copy()
        ydl_opts['outtmpl'] = os.path.join(out_path, '%(id)s.%(ext)s')
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            # СУПЕР-БЫСТРЫЙ ПОИСК ФАЙЛОВ
            files = []
            if info.get('requested_downloads'):
                for download in info['requested_downloads']:
                    file_path = download['filepath']
                    if os.path.exists(file_path) and os.path.getsize(file_path) > 5000:  # Минимум 5KB
                        files.append(file_path)
            
            # ЕСЛИ НЕТ ФАЙЛОВ - БЫСТРЫЙ ПОИСК В ДИРЕКТОРИИ
            if not files:
                for file in os.listdir(out_path):
                    if len(files) >= 10:  # ОГРАНИЧИВАЕМ ДЛЯ СКОРОСТИ
                        break
                    file_path = os.path.join(out_path, file)
                    if (os.path.isfile(file_path) and 
                        os.path.getsize(file_path) > 5000 and
                        self._is_media_file_ultra_fast(file_path)):
                        files.append(file_path)
            
            # МГНОВЕННОЕ ОПРЕДЕЛЕНИЕ ТИПА
            content_type = 'photo'
            if files:
                first_file = files[0].lower()
                if any(first_file.endswith(ext) for ext in ['.mp4', '.mov', '.avi']):
                    content_type = 'video'
                if len(files) > 1:
                    content_type = 'carousel'
            
            return {
                'type': content_type,
                'files': files,
                'title': 'instagram_content',
                'webpage_url': url
            }

    def _download_no_cookies(self, url: str, out_path: str):
        """Быстрый метод без cookies"""
        ydl_opts = self.ultra_fast_ydl_opts.copy()
        ydl_opts['outtmpl'] = os.path.join(out_path, '%(id)s.%(ext)s')
        ydl_opts.pop('cookiefile', None)  # Убираем cookies
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            files = []
            for file in os.listdir(out_path):
                if len(files) >= 10:
                    break
                file_path = os.path.join(out_path, file)
                if (os.path.isfile(file_path) and 
                    os.path.getsize(file_path) > 5000 and
                    self._is_media_file_ultra_fast(file_path)):
                    files.append(file_path)
            
            content_type = 'photo'
            if files:
                first_file = files[0].lower()
                if any(first_file.endswith(ext) for ext in ['.mp4', '.mov', '.avi']):
                    content_type = 'video'
                if len(files) > 1:
                    content_type = 'carousel'
            
            return {
                'type': content_type,
                'files': files,
                'title': 'instagram_content',
                'webpage_url': url
            }

    def _is_media_file_ultra_fast(self, file_path: str) -> bool:
        """УЛЬТРА-БЫСТРАЯ проверка"""
        ext = os.path.splitext(file_path)[1].lower()
        return ext in {'.jpg', '.jpeg', '.png', '.mp4', '.mov', '.avi'}

# ------------------------- УПРОЩЕННЫЕ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ -------------------------
def extract_url_fast(text: str) -> str:
    match = re.search(r"https?://[^\s]+", text)
    return match.group(0) if match else ""

async def ultra_fast_cleanup(dir_path: str):
    """ОЧЕНЬ БЫСТРАЯ очистка в фоне"""
    try:
        if os.path.exists(dir_path):
            # НЕМЕДЛЕННАЯ ОЧИСТКА БЕЗ ОЖИДАНИЯ
            shutil.rmtree(dir_path, ignore_errors=True)
    except:
        pass

def check_cookies_fast():
    return os.path.exists("cookies.txt")

# ------------------------- УЛЬТРА-БЫСТРЫЕ ОБРАБОТЧИКИ -------------------------
@app.on_message(filters.command("start"))
async def start_ultra_fast(client, message):
    await message.reply_text(
        "⚡⚡ **ULTRA FAST Instagram Downloader** ⚡⚡\n\n"
        "Отправь ссылку → Получи контент МГНОВЕННО!"
    )

@app.on_message(filters.text & filters.private)
async def handle_text_ultra_fast(client, message):
    user_id = message.from_user.id
    
    # СУПЕР-БЫСТРАЯ ПРОВЕРКА
    url = extract_url_fast(message.text)
    if not url or "instagram.com" not in url:
        return

    # ПРОВЕРКА АКТИВНОЙ ОБРАБОТКИ
    if user_processing.get(user_id):
        try:
            temp_msg = await message.reply_text("⚡ Уже скачиваю...")
            await asyncio.sleep(1)
            await temp_msg.delete()
        except:
            pass
        return
    
    user_processing[user_id] = True
    status = None
    tmp_dir = None
    
    try:
        status = await message.reply_text("⚡ Скачиваю...")
        tmp_dir = tempfile.mkdtemp()
        
        # ИСПОЛЬЗУЕМ УЛЬТРА-БЫСТРЫЙ ЗАГРУЗЧИК
        downloader = UltraFastInstagramDownloader()
        content_info = await downloader.download_instagram_content(url, tmp_dir)
        
        if not content_info.get('files'):
            raise Exception("No files")
        
        await status.edit_text("📤 Отправляю...")
        
        # МГНОВЕННАЯ ОТПРАВКА
        await send_ultra_fast(message, content_info)
        
        # СРАЗУ УДАЛЯЕМ СООБЩЕНИЕ ПОЛЬЗОВАТЕЛЯ
        await message.delete()
        
    except Exception as e:
        try:
            await message.reply_text(f"❌ {str(e)[:80]}")
            await asyncio.sleep(2)
            await message.delete()
        except:
            pass
    finally:
        if status:
            try:
                await status.delete()
            except:
                pass
        if tmp_dir:
            await ultra_fast_cleanup(tmp_dir)
        user_processing[user_id] = False

async def send_ultra_fast(message, content_info):
    """УЛЬТРА-БЫСТРАЯ отправка"""
    files = content_info['files'][:10]  # ОГРАНИЧИВАЕМ КОЛИЧЕСТВО
    content_type = content_info['type']
    
    if content_type == 'carousel' and len(files) > 1:
        # ДЛЯ КАРУСЕЛИ - СРАЗУ МЕДИАГРУППА
        await send_media_group_ultra_fast(message, files)
    else:
        # ДЛЯ ОДИНОЧНЫХ ФАЙЛОВ - ПАРАЛЛЕЛЬНАЯ ОТПРАВКА
        await send_parallel_ultra_fast(message, files, content_type)

async def send_media_group_ultra_fast(message, files):
    """САМАЯ БЫСТРАЯ отправка медиагруппы"""
    media_group = []
    
    for i, file_path in enumerate(files[:10]):
        if not os.path.exists(file_path):
            continue
            
        file_lower = file_path.lower()
        try:
            if file_lower.endswith(('.jpg', '.jpeg', '.png')):
                media_item = InputMediaPhoto(file_path)
                if i == 0:
                    media_item.caption = "📸 Instagram"
                media_group.append(media_item)
            elif file_lower.endswith(('.mp4', '.mov', '.avi')):
                media_item = InputMediaVideo(file_path)
                if i == 0:
                    media_item.caption = "🎥 Instagram"
                media_group.append(media_item)
        except:
            continue
    
    if media_group:
        try:
            await message.reply_media_group(media_group)
        except:
            # ЕСЛИ МЕДИАГРУППА НЕ СРАБОТАЛА - ПАРАЛЛЕЛЬНАЯ ОТПРАВКА
            await send_parallel_ultra_fast(message, files, 'carousel')

async def send_parallel_ultra_fast(message, files, content_type):
    """УЛЬТРА-БЫСТРАЯ параллельная отправка"""
    tasks = []
    
    for file_path in files[:5]:  # ОГРАНИЧИВАЕМ ДЛЯ СКОРОСТИ
        if not os.path.exists(file_path):
            continue
            
        file_lower = file_path.lower()
        if file_lower.endswith(('.jpg', '.jpeg', '.png')):
            tasks.append(message.reply_photo(file_path, caption="📸 Instagram"))
        elif file_lower.endswith(('.mp4', '.mov', '.avi')):
            tasks.append(message.reply_video(file_path, caption="🎥 Instagram"))
    
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

# ------------------------- ЗАПУСК -------------------------
if __name__ == "__main__":
    # СОЗДАЕМ ДИРЕКТОРИИ
    os.makedirs("dl", exist_ok=True)
    
    print("🚀🚀 ULTRA FAST BOT STARTING... 🚀🚀")
    app.run()
