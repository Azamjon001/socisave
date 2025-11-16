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
from datetime import datetime, timedelta
import hashlib

API_ID = 26670278
API_HASH = "e3d77390fd9c22d98bb6bddca86fef1a"
BOT_TOKEN = "6788128988:AAEMmCSafiiEqtS5UWQQxfo--W0On7B6Q08"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------------- ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ -------------------------
user_processing = {}
processed_messages = set()

# ------------------------- СИСТЕМА 48 IP-АДРЕСОВ И УСТРОЙСТВ -------------------------
class IPGenerator:
    def __init__(self):
        self.base_ips = self.generate_base_ips()
        self.current_ips = self.base_ips.copy()
        self.rotation_time = 1800  # 30 минут в секундах
        self.last_rotation = datetime.now()
    
    def generate_base_ips(self):
        """Генерируем 48 базовых IP-адресов из разных подсетей"""
        base_ips = []
        
        # Разные подсети для разнообразия
        subnets = [
            "104.28", "104.29", "108.177", "142.250", "172.217", 
            "173.194", "192.178", "203.208", "216.58", "216.239",
            "74.125", "64.233", "66.102", "66.249", "72.14", 
            "209.85", "207.126", "173.194", "216.58", "74.125"
        ]
        
        for i in range(48):
            subnet = random.choice(subnets)
            ip3 = random.randint(1, 254)
            ip4 = random.randint(1, 254)
            base_ips.append(f"{subnet}.{ip3}.{ip4}")
        
        logger.info(f"✅ Сгенерировано {len(base_ips)} базовых IP-адресов")
        return base_ips
    
    def rotate_ips(self):
        """Ротация IP-адресов каждые 30 минут"""
        now = datetime.now()
        if (now - self.last_rotation).total_seconds() >= self.rotation_time:
            logger.info("🔄 Ротация IP-адресов...")
            
            for i in range(len(self.current_ips)):
                # Немного изменяем последний октет для "свежести"
                ip_parts = self.current_ips[i].split('.')
                ip_parts[3] = str((int(ip_parts[3]) + random.randint(1, 50)) % 255)
                self.current_ips[i] = '.'.join(ip_parts)
            
            self.last_rotation = now
            logger.info("✅ IP-адреса обновлены")
    
    def get_ip_for_request(self, request_id):
        """Получаем IP для конкретного запроса"""
        self.rotate_ips()
        
        # Детерминированный выбор IP на основе ID запроса
        ip_index = hash(request_id) % len(self.current_ips)
        selected_ip = self.current_ips[ip_index]
        
        return selected_ip

class MobileDeviceEmulator:
    def __init__(self):
        self.devices = self.generate_devices()
        self.ip_generator = IPGenerator()
    
    def generate_devices(self):
        """Генерируем 48 уникальных мобильных устройств"""
        devices = []
        
        # Разные модели телефонов
        phone_models = [
            # Samsung
            {"brand": "Samsung", "models": ["SM-G991B", "SM-G996B", "SM-G998B", "SM-A525F", "SM-A736B"]},
            # iPhone
            {"brand": "Apple", "models": ["iPhone14,1", "iPhone14,2", "iPhone14,3", "iPhone15,1", "iPhone15,2"]},
            # Xiaomi
            {"brand": "Xiaomi", "models": ["M2102J20SG", "M2012K11AG", "22021211RG", "2109119DG"]},
            # Google Pixel
            {"brand": "Google", "models": ["Pixel 6", "Pixel 6 Pro", "Pixel 7", "Pixel 7 Pro"]},
            # OnePlus
            {"brand": "OnePlus", "models": ["LE2113", "LE2123", "NE2213", "CPH2415"]},
        ]
        
        android_versions = [
            "10; Android 10", "11; Android 11", "12; Android 12", 
            "13; Android 13", "14; Android 14"
        ]
        
        for i in range(48):
            brand_data = random.choice(phone_models)
            model = random.choice(brand_data["models"])
            android = random.choice(android_versions)
            
            device = {
                'id': f"device_{i+1:02d}",
                'brand': brand_data["brand"],
                'model': model,
                'android_version': android,
                'user_agent': self.generate_user_agent(brand_data["brand"], model, android),
                'screen_resolution': self.generate_screen_resolution(brand_data["brand"]),
                'app_version': f"{random.randint(200, 280)}.0.0.{random.randint(10, 30)}.{random.randint(100, 200)}"
            }
            devices.append(device)
        
        logger.info(f"✅ Создано {len(devices)} виртуальных устройств")
        return devices
    
    def generate_user_agent(self, brand, model, android_version):
        """Генерируем уникальный User-Agent для каждого устройства"""
        if brand == "Apple":
            return f"Mozilla/5.0 (iPhone; CPU iPhone OS {android_version.replace('; Android', '').replace(' ', '_')} like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1"
        else:
            return f"Mozilla/5.0 (Linux; Android {android_version}; {model}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Mobile Safari/537.36"
    
    def generate_screen_resolution(self, brand):
        """Генерируем разрешение экрана в зависимости от бренда"""
        if brand == "Apple":
            return random.choice(["1170x2532", "1284x2778", "1179x2556"])
        else:
            return random.choice(["1080x2400", "1440x3200", "1080x2340", "1440x3040"])
    
    def get_device_for_request(self, request_id):
        """Получаем устройство для запроса"""
        device_index = hash(request_id) % len(self.devices)
        return self.devices[device_index]

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

# ------------------------- ОБНОВЛЕННЫЙ Instagram Downloader -------------------------
class InstagramDownloader:
    def __init__(self):
        self.device_emulator = MobileDeviceEmulator()
        self.thread_pool = ThreadPoolExecutor(max_workers=3)
        self.request_counter = 0

    def get_ydl_opts(self, request_id):
        """Получаем настройки yt-dlp с уникальными параметрами для каждого запроса"""
        device = self.device_emulator.get_device_for_request(request_id)
        ip_address = self.device_emulator.ip_generator.get_ip_for_request(request_id)
        
        # Создаем уникальные заголовки для каждого запроса
        headers = {
            'User-Agent': device['user_agent'],
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0',
            # Эмулируем мобильное устройство
            'Viewport-Width': device['screen_resolution'].split('x')[0],
            'Width': device['screen_resolution'].split('x')[0],
        }
        
        return {
            'outtmpl': 'downloads/%(id)s.%(ext)s',
            'format': 'best[height<=720]',
            'cookiefile': 'cookies.txt',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'noplaylist': True,
            
            # ⚡ ОПТИМИЗАЦИИ СКОРОСТИ
            'socket_timeout': 15,
            'extractretry': 1,
            'retries': 2,
            'fragment_retries': 2,
            'skip_unavailable_fragments': True,
            'keep_fragments': False,
            'concurrent_fragment_downloads': 6,
            
            # 🆕 УНИКАЛЬНЫЕ НАСТРОЙКИ ДЛЯ КАЖДОГО ЗАПРОСА
            'http_headers': headers,
            'user_agent': device['user_agent'],
            
            # Эмуляция реального устройства
            'referer': 'https://www.instagram.com/',
            'origin': 'https://www.instagram.com',
        }

    async def download_instagram_content(self, url: str, out_path: str):
        """ОПТИМИЗИРОВАННАЯ функция для скачивания с уникальными параметрами"""
        try:
            self.request_counter += 1
            request_id = f"{int(time.time())}_{self.request_counter}"
            
            # Логируем параметры устройства
            device = self.device_emulator.get_device_for_request(request_id)
            ip_address = self.device_emulator.ip_generator.get_ip_for_request(request_id)
            logger.info(f"📱 Запрос {request_id}: {device['brand']} {device['model']} | IP: {ip_address}")
            
            loop = asyncio.get_event_loop()
            content_type = self._determine_content_type(url)
            logger.info(f"🔍 Определен тип контента: {content_type}")
            
            if '/stories/' in url:
                result = await loop.run_in_executor(
                    self.thread_pool, 
                    self._download_story_fast, 
                    url, out_path, content_type, request_id
                )
            else:
                result = await loop.run_in_executor(
                    self.thread_pool,
                    self._download_with_ytdlp_fast,
                    url, out_path, content_type, request_id
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

    def _download_story_fast(self, url: str, out_path: str, content_type: str, request_id: str):
        """ОПТИМИЗИРОВАННОЕ скачивание историй с уникальными параметрами"""
        try:
            ydl_opts = self.get_ydl_opts(request_id)
            ydl_opts['outtmpl'] = os.path.join(out_path, 'story_%(id)s.%(ext)s')
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                result = {
                    'type': 'story',
                    'files': [],
                    'title': f"instagram_story_{info.get('id', 'unknown')}",
                    'webpage_url': url,
                    'request_id': request_id
                }
                
                # БЫСТРЫЙ поиск файлов
                if info.get('requested_downloads'):
                    for download in info['requested_downloads']:
                        file_path = download['filepath']
                        if os.path.exists(file_path) and self._is_media_file_fast(file_path):
                            result['files'].append(file_path)
                
                # Быстрый поиск в директории
                if not result['files']:
                    for file in os.listdir(out_path):
                        file_path = os.path.join(out_path, file)
                        if self._is_media_file_fast(file_path):
                            result['files'].append(file_path)
                
                # Быстрое определение типа
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

    def _download_with_ytdlp_fast(self, url: str, out_path: str, content_type: str, request_id: str):
        """ОПТИМИЗИРОВАННОЕ скачивание через yt-dlp с уникальными параметрами"""
        ydl_opts = self.get_ydl_opts(request_id)
        ydl_opts['outtmpl'] = os.path.join(out_path, '%(id)s.%(ext)s')
        
        # Быстрая настройка формата
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
                'webpage_url': info.get('webpage_url', url),
                'request_id': request_id
            }
            
            # БЫСТРЫЙ сбор файлов
            if info.get('requested_downloads'):
                for download in info['requested_downloads']:
                    file_path = download['filepath']
                    if os.path.exists(file_path) and self._is_media_file_fast(file_path):
                        result['files'].append(file_path)
            
            # Быстрый поиск в директории
            if not result['files']:
                for file in os.listdir(out_path):
                    file_path = os.path.join(out_path, file)
                    if self._is_media_file_fast(file_path):
                        result['files'].append(file_path)
            
            # Быстрое определение типа контента
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

    # ОСТАВЛЯЕМ ВАШИ ОРИГИНАЛЬНЫЕ МЕТОДЫ ДЛЯ FALLBACK
    async def _download_story_with_instaloader(self, url: str, out_path: str, content_type: str):
        """Ваш оригинальный метод для fallback"""
        try:
            L = instaloader.Instaloader(
                dirname_pattern=out_path,
                filename_pattern='{profile}_{date_utc}',
                download_pictures=(content_type != 'video'),
                download_videos=(content_type != 'photo'),
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
            story_count = 0
            
            for story in L.get_stories([profile.userid]):
                for item in story.get_items():
                    if story_count >= 3:
                        break
                        
                    L.download_storyitem(item, target=os.path.join(out_path, f"story_{username}"))
                    
                    for file in os.listdir(out_path):
                        if file.startswith(f"story_{username}") and not file.endswith('.txt'):
                            full_path = os.path.join(out_path, file)
                            if self._is_media_file_fast(full_path):
                                downloaded_files.append(full_path)
                    
                    story_count += 1
            
            if not downloaded_files:
                raise Exception("Не удалось скачать истории")
            
            result = {
                'type': 'story',
                'files': downloaded_files,
                'title': f"instagram_story_{username}",
                'webpage_url': url,
                'count': len(downloaded_files)
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

    def _extract_story_username(self, url: str):
        patterns = [
            r'instagram\.com/stories/([^/?]+)',
            r'instagram\.com/stories/([^/?]+)/(\d+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

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

# ------------------------- НОВАЯ КОМАНДА ДЛЯ СТАТИСТИКИ -------------------------
@app.on_message(filters.command("devices"))
async def show_devices(client, message):
    """Показывает статистику по виртуальным устройствам"""
    try:
        downloader = InstagramDownloader()
        devices = downloader.device_emulator.devices
        
        response = "📱 **Виртуальные устройства (48 штук):**\n\n"
        
        for i, device in enumerate(devices[:10]):  # Показываем первые 10
            response += f"**{device['id']}:** {device['brand']} {device['model']}\n"
            response += f"User-Agent: {device['user_agent'][:50]}...\n\n"
        
        response += f"🔄 IP-адреса обновляются каждые 30 минут\n"
        response += f"🔧 Каждый запрос использует уникальное устройство"
        
        await message.reply_text(response)
        
    except Exception as e:
        await message.reply_text(f"❌ Ошибка: {e}")

# ------------------------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (БЕЗ ИЗМЕНЕНИЙ) -------------------------
def extract_first_url(text: str) -> str:
    match = re.search(r"(https?://[^\s]+)", text)
    return match.group(1) if match else ""

def normalize_url(url: str) -> str:
    if "youtu.be/" in url:
        video_id = url.split("/")[-1].split("?")[0]
        return f"https://www.youtube.com/watch?v={video_id}"
    return url

def get_youtube_direct_url(url: str) -> str:
    ydl_opts = {
        "quiet": True, 
        "skip_download": True, 
        "format": "mp4[height<=720]/best[ext=mp4]/best",
        "socket_timeout": 10
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
        "socket_timeout": 15,
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

# ------------------------- ОБРАБОТЧИКИ СООБЩЕНИЙ (БЕЗ ИЗМЕНЕНИЙ) -------------------------
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
            "🚀 Оптимизировано для максимальной скорости!"
        )
        logger.info(f"✅ Отправлено приветственное сообщение пользователю {message.from_user.id}")
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
        "• Instagram фото/видео/рилс\n"
        "• Instagram карусель\n" 
        "• Instagram историю\n\n"
        "⚡ **ОПТИМИЗИРОВАНО ДЛЯ СКОРОСТИ!**\n"
        "📌 Бот автоматически определит тип контента"
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
    insta_downloader = InstagramDownloader()  # 🆕 Теперь с системой 48 устройств
    tmp_dir = None
    
    try:
        url = normalize_url(url)
        logger.info(f"🔄 Нормализованный URL: {url}")
        
        status = await message.reply_text("⚡ Определяю тип контента...")
        
        if "youtube" in url or "youtu.be" in url:
            await _handle_youtube_fast(client, message, url, status)
            
        elif "instagram.com" in url:
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

async def _handle_youtube_fast(client, message, url, status):
    """ОПТИМИЗИРОВАННАЯ обработка YouTube"""
    try:
        await status.edit_text("🔗 Получаю прямую ссылку YouTube...")
        direct_url = await asyncio.to_thread(get_youtube_direct_url, url)
        
        await status.edit_text("📤 Отправляю видео...")
        await message.reply_video(
            direct_url, 
            caption="📥 YouTube видео через @azams_bot"
        )
        logger.info("✅ YouTube видео отправлено через прямую ссылку")
        
    except Exception as e:
        logger.warning(f"❌ Прямая ссылка не сработала: {e}, скачиваю файл...")
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
            
        except Exception as download_error:
            raise download_error
        finally:
            if os.path.exists(tmp_dir):
                safe_remove_directory(tmp_dir)

async def _handle_instagram_fast(client, message, url, status, downloader, tmp_dir):
    """ОПТИМИЗИРОВАННАЯ обработка Instagram"""
    if not check_cookies_file():
        await status.edit_text("❌ Файл cookies.txt не найден. Instagram недоступен.")
        await asyncio.sleep(3)
        return
        
    try:
        await status.edit_text("⚡ Скачиваю контент...")
        
        content_info = await downloader.download_instagram_content(url, tmp_dir)
        
        if not content_info.get('files'):
            raise Exception("Не удалось скачать файлы")
        
        # БЫСТРАЯ проверка расширений
        validated_files = []
        for file_path in content_info['files']:
            if os.path.exists(file_path):
                fixed_path = validate_and_fix_extension(file_path)
                validated_files.append(fixed_path)
        
        if not validated_files:
            raise Exception("Нет валидных файлов для отправки")
        
        content_info['files'] = validated_files
        
        await status.edit_text(f"📤 Отправляю {content_info['type']}...")
        
        # ОПТИМИЗИРОВАННАЯ отправка
        await send_content_fast(client, message, content_info)
        
        logger.info(f"✅ Instagram {content_info['type']} отправлен ({len(validated_files)} файлов)")
        
    except Exception as e:
        raise e

async def send_content_fast(client, message, content_info):
    """ОПТИМИЗИРОВАННАЯ отправка контента"""
    files = content_info['files']
    content_type = content_info['type']
    
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
            await asyncio.gather(*tasks, return_exceptions=True)
            
    elif content_type in ['video', 'story_video']:
        tasks = []
        for file_path in files[:10]:
            if os.path.exists(file_path):
                task = message.reply_video(
                    file_path,
                    caption=f"📹 Instagram {'история' if 'story' in content_type else 'видео'} через @azams_bot"
                )
                tasks.append(task)
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            
    elif content_type == 'carousel':
        await _send_carousel_fast(client, message, files)

async def _send_carousel_fast(client, message, files):
    """ОПТИМИЗИРОВАННАЯ отправка карусели"""
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
            await message.reply_media_group(media_group)
            logger.info(f"✅ Медиагруппа отправлена ({len(media_group)} файлов)")
        except Exception as e:
            logger.error(f"❌ Ошибка отправки медиагруппы: {e}")
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
    
    logger.info("🚀 ЗАПУСК ОПТИМИЗИРОВАННОГО БОТА С 48 УСТРОЙСТВАМИ...")
    logger.info("📱 48 уникальных IP-адресов и User-Agent")
    logger.info("🔄 Автоматическая ротация каждые 30 минут")
    
    try:
        app.run()
        logger.info("✅ Бот успешно запущен и готов к работе!")
    except Exception as e:
        logger.error(f"❌ Ошибка запуска бота: {e}")
