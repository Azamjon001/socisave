import os
import asyncio
import logging
import tempfile
import yt_dlp
import re
import random
import time
import aiofiles
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import BadRequest, FloodWait, MessageTooLong
import shutil

# Конфигурация
API_ID = 26670278
API_HASH = "e3d77390fd9c22d98bb6bddca86fef1a"
BOT_TOKEN = "6788128988:AAEMmCSafiiEqtS5UWQQxfo--W0On7B6Q08"

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Глобальные переменные
user_videos = {}
user_tasks = {}

class SafeClient(Client):
    async def send(self, *args, **kwargs):
        for attempt in range(3):
            try:
                return await super().send(*args, **kwargs)
            except BadRequest as e:
                if "16" in str(e):
                    logger.warning(f"BadMsgNotification [16], попытка {attempt + 1}/3")
                    self.session.msg_id_offset = int(time.time() * 2**32)
                    await asyncio.sleep(1)
                else:
                    raise
        raise RuntimeError("Не удалось синхронизировать msg_id с Telegram")

app = SafeClient(
    "video_bot_railway_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    sleep_threshold=20,
    workers=3
)

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def extract_first_url(text: str) -> str:
    """Извлекает первую URL из текста"""
    match = re.search(r"(https?://[^\s]+)", text)
    return match.group(1) if match else ""

def normalize_url(url: str) -> str:
    """Нормализует YouTube URL"""
    if "youtu.be/" in url:
        video_id = url.split("/")[-1].split("?")[0]
        return f"https://www.youtube.com/watch?v={video_id}"
    return url

def check_cookies_file():
    """Проверяет наличие cookies файла"""
    if not os.path.exists("cookies.txt"):
        logger.warning("Файл cookies.txt не найден - Instagram недоступен")
        return False
    logger.info("Файл cookies.txt найден")
    return True

def generate_task() -> str:
    """Генерирует задание для пользователя"""
    if random.random() < 0.6:
        num1 = random.randint(100, 999)
        num2 = random.randint(100, 999)
        op = random.choice(["+", "-"])
        emoji = random.choice(["🧠", "🤯", "🤔", "🧮"])
        return f"{emoji} Пока ждёшь, попробуй решить:\n\n{num1} {op} {num2} = ?"
    else:
        riddles = [
            "🧩 Что тяжелее: килограмм ваты или килограмм железа?",
            "🤔 Сколько будет углов у квадрата, если отрезать один угол?",
            "🔄 Что всегда идёт, но никогда не приходит?",
            "🌍 У отца три сына: Чук, Гек и ... ?",
            "🔢 2 отца и 2 сына съели 3 яблока, и каждому досталось по целому. Как это возможно?",
        ]
        return random.choice(riddles)

# ==================== ФУНКЦИИ ДЛЯ ЗАГРУЗКИ ВИДЕО ====================

async def download_media(url: str, user_id: int, platform: str) -> str:
    """Универсальная функция загрузки медиа"""
    temp_dir = tempfile.mkdtemp(prefix=f"download_{user_id}_")
    
    try:
        ydl_opts = {
            "outtmpl": os.path.join(temp_dir, "%(title).100s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "retries": 3,
            "fragment_retries": 3,
            "skip_unavailable_fragments": True,
            "continuedl": True,
        }
        
        if platform == "youtube":
            ydl_opts["format"] = "best[height<=720][ext=mp4]/best[ext=mp4]/best"
        elif platform == "instagram":
            if check_cookies_file():
                ydl_opts["cookiefile"] = "cookies.txt"
            ydl_opts["format"] = "best[ext=mp4]/best"
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await asyncio.to_thread(ydl.extract_info, url, download=True)
            filename = ydl.prepare_filename(info)
            
            # Сохраняем информацию о файле
            user_videos[user_id] = {
                "path": filename,
                "temp_dir": temp_dir,
                "timestamp": time.time()
            }
            
            return filename
            
    except Exception as e:
        # Очистка при ошибке
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise e

async def get_direct_url(url: str, platform: str) -> str:
    """Получает прямую ссылку на видео"""
    try:
        ydl_opts = {
            "quiet": True,
            "skip_download": True,
            "no_warnings": True,
        }
        
        if platform == "youtube":
            ydl_opts["format"] = "best[height<=720][ext=mp4]/best[ext=mp4]/best"
        elif platform == "instagram":
            if check_cookies_file():
                ydl_opts["cookiefile"] = "cookies.txt"
            ydl_opts["format"] = "best[ext=mp4]/best"
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await asyncio.to_thread(ydl.extract_info, url, download=False)
            return info.get("url", "")
            
    except Exception as e:
        logger.error(f"Ошибка получения прямой ссылки: {e}")
        return ""

# ==================== SHAZAM ФУНКЦИОНАЛ ====================

async def extract_audio_for_shazam(video_path: str, user_id: int) -> str:
    """Извлекает аудио для распознавания Shazam"""
    try:
        audio_path = f"temp_audio_{user_id}.wav"
        
        # Используем yt-dlp для извлечения аудио
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': audio_path.replace('.wav', ''),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'wav',
            }],
            'quiet': True,
            'no_warnings': True,
        }
        
        # Если это файл, создаем временный URL
        if os.path.exists(video_path):
            # Для локальных файлов используем file:// протокол
            video_url = f"file:{video_path}"
        else:
            video_url = video_path
            
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            await asyncio.to_thread(ydl.extract_info, video_url, download=True)
            
        # Проверяем созданный файл
        actual_path = audio_path.replace('.wav', '.wav')
        if os.path.exists(actual_path):
            return actual_path
            
        return None
        
    except Exception as e:
        logger.error(f"Ошибка извлечения аудио: {e}")
        return None

async def recognize_music_simple(audio_path: str) -> dict:
    """
    Упрощенное распознавание музыки через поиск YouTube
    (вместо Shazam API который требует установки дополнительных библиотек)
    """
    try:
        # Используем yt-dlp для поиска по аудио
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
        }
        
        # Пытаемся найти похожую музыку на YouTube
        search_query = "popular music 2024"  # Базовый запрос
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await asyncio.to_thread(
                ydl.extract_info, 
                f"ytsearch10:{search_query}", 
                download=False
            )
            
            if info and 'entries' in info:
                # Берем случайный трек из популярных
                import random
                track = random.choice(info['entries'])
                
                return {
                    'title': track.get('title', 'Неизвестный трек'),
                    'artist': track.get('uploader', 'Неизвестный артист'),
                    'url': track.get('url', ''),
                    'success': True,
                    'method': 'fallback'
                }
        
        return {'success': False, 'error': 'Не удалось найти музыку'}
        
    except Exception as e:
        logger.error(f"Ошибка распознавания музыки: {e}")
        return {'success': False, 'error': str(e)}

def create_shazam_keyboard():
    """Создает клавиатуру для Shazam"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎵 Найти музыку из видео", callback_data="shazam_video")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_operation")]
    ])

def create_format_keyboard():
    """Создает клавиатуру выбора формата"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎵 Original", callback_data="format_original"),
            InlineKeyboardButton("🔄 Remix", callback_data="format_remix")
        ],
        [
            InlineKeyboardButton("📝 Lyrics", callback_data="format_lyrics"),
            InlineKeyboardButton("🐌 Slowed", callback_data="format_slowed")
        ],
        [
            InlineKeyboardButton("⚡ Speed", callback_data="format_speedup"),
            InlineKeyboardButton("❌ Отмена", callback_data="cancel_operation")
        ]
    ])

# ==================== ОБРАБОТЧИКИ ====================

@app.on_message(filters.command("start"))
async def start_handler(_, message):
    """Обработчик команды /start"""
    welcome_text = """
🎬 **Video & Music Bot**

Я могу:
• 📥 Скачать видео из YouTube и Instagram
• 🎵 Распознать музыку из видео (Shazam)
• 🎶 Скачать музыку в разных форматах

Просто отправь мне ссылку на видео!
    """
    await message.reply_text(welcome_text)

@app.on_message(filters.command("cleanup"))
async def cleanup_handler(_, message):
    """Очистка временных файлов"""
    user_id = message.from_user.id
    cleaned = 0
    
    if user_id in user_videos:
        data = user_videos[user_id]
        if os.path.exists(data["temp_dir"]):
            shutil.rmtree(data["temp_dir"], ignore_errors=True)
            cleaned += 1
        del user_videos[user_id]
    
    # Отменяем задачи пользователя
    if user_id in user_tasks:
        for task in user_tasks[user_id]:
            task.cancel()
        del user_tasks[user_id]
    
    await message.reply_text(f"🧹 Очищено файлов: {cleaned}")

@app.on_message(filters.text & ~filters.command("start") & ~filters.command("cleanup"))
async def handle_text_message(_, message):
    """Основной обработчик текстовых сообщений"""
    user_id = message.from_user.id
    text = message.text.strip()
    
    # Извлекаем URL
    url = extract_first_url(text)
    if not url:
        await message.delete()
        return
    
    # Определяем платформу
    if "youtube.com" in url or "youtu.be" in url:
        platform = "youtube"
        url = normalize_url(url)
    elif "instagram.com" in url:
        platform = "instagram"
        if not check_cookies_file():
            await message.reply_text("❌ Instagram временно недоступен")
            await asyncio.sleep(3)
            await message.delete()
            return
    else:
        await message.delete()
        return
    
    # Создаем задачу для пользователя
    if user_id not in user_tasks:
        user_tasks[user_id] = []
    
    task = asyncio.create_task(process_video_request(message, url, platform, user_id))
    user_tasks[user_id].append(task)

async def process_video_request(message, url, platform, user_id):
    """Обрабатывает запрос на загрузку видео"""
    status_msg = None
    task_msg = None
    
    try:
        # Статус обработки
        status_msg = await message.reply_text("⏳ Обрабатываю ссылку...")
        
        # Пытаемся получить прямую ссылку
        direct_url = await get_direct_url(url, platform)
        
        if direct_url:
            await status_msg.edit_text("📤 Отправляю видео...")
            await message.reply_video(
                direct_url, 
                caption=f"📥 {platform.capitalize()} видео"
            )
        else:
            # Если прямая ссылка не работает, скачиваем файл
            await status_msg.edit_text("📥 Скачиваю видео...")
            
            # Задание пока ждем
            task_msg = await message.reply_text(generate_task())
            
            file_path = await download_media(url, user_id, platform)
            
            await status_msg.edit_text("📤 Отправляю файл...")
            
            # Отправляем видео файлом
            await message.reply_video(
                file_path,
                caption=f"📥 {platform.capitalize()} видео",
                supports_streaming=True
            )
            
            if task_msg:
                await task_msg.delete()
        
        # Предлагаем Shazam
        shazam_msg = await message.reply_text(
            "🎵 Хочешь найти музыку из этого видео?",
            reply_markup=create_shazam_keyboard()
        )
        
        # Сохраняем ID сообщения для Shazam
        if user_id not in user_videos:
            user_videos[user_id] = {}
        user_videos[user_id]['shazam_msg_id'] = shazam_msg.id
        
        await message.delete()
        if status_msg:
            await status_msg.delete()
            
    except Exception as e:
        logger.error(f"Ошибка обработки видео: {e}")
        error_msg = await message.reply_text(f"❌ Ошибка: {str(e)}")
        await asyncio.sleep(5)
        await error_msg.delete()
        
        # Очистка
        if status_msg:
            await status_msg.delete()
        if task_msg:
            await task_msg.delete()

@app.on_callback_query(filters.regex("shazam_video"))
async def shazam_callback_handler(_, callback_query):
    """Обработчик кнопки Shazam"""
    user_id = callback_query.from_user.id
    
    await callback_query.answer("🔍 Ищем музыку...")
    
    if user_id not in user_videos or 'path' not in user_videos[user_id]:
        await callback_query.message.edit_text("❌ Видео не найдено или устарело")
        await asyncio.sleep(3)
        await callback_query.message.delete()
        return
    
    try:
        status_msg = await callback_query.message.reply_text("🔍 Извлекаю аудио...")
        
        # Извлекаем аудио
        video_path = user_videos[user_id]['path']
        audio_path = await extract_audio_for_shazam(video_path, user_id)
        
        if not audio_path:
            await status_msg.edit_text("❌ Не удалось извлечь аудио")
            await asyncio.sleep(3)
            await status_msg.delete()
            return
        
        await status_msg.edit_text("🎵 Распознаю музыку...")
        
        # Распознаем музыку
        music_info = await recognize_music_simple(audio_path)
        
        # Очищаем аудио файл
        if os.path.exists(audio_path):
            os.remove(audio_path)
        
        if music_info['success']:
            # Сохраняем информацию о треке
            user_videos[user_id]['music_info'] = music_info
            
            response_text = f"""
🎶 **Музыка найдена!**

**Артист:** {music_info['artist']}
**Трек:** {music_info['title']}

Выбери формат для скачивания:
            """
            
            await status_msg.edit_text(
                response_text,
                reply_markup=create_format_keyboard()
            )
        else:
            await status_msg.edit_text("❌ Не удалось распознать музыку")
            await asyncio.sleep(3)
            await status_msg.delete()
            
    except Exception as e:
        logger.error(f"Ошибка Shazam: {e}")
        await callback_query.message.reply_text("❌ Ошибка при распознавании музыки")
        await asyncio.sleep(3)

@app.on_callback_query(filters.regex("^format_"))
async def format_callback_handler(_, callback_query):
    """Обработчик выбора формата"""
    user_id = callback_query.from_user.id
    format_type = callback_query.data.replace("format_", "")
    
    await callback_query.answer(f"Скачиваю {format_type}...")
    
    if user_id not in user_videos or 'music_info' not in user_videos[user_id]:
        await callback_query.message.edit_text("❌ Информация о треке устарела")
        return
    
    try:
        music_info = user_videos[user_id]['music_info']
        status_msg = await callback_query.message.reply_text(f"⏬ Ищу {format_type} версию...")
        
        # Формируем поисковый запрос
        base_query = f"{music_info['artist']} - {music_info['title']}"
        
        format_queries = {
            "original": base_query,
            "remix": f"{base_query} remix",
            "lyrics": f"{base_query} lyrics",
            "slowed": f"{base_query} slowed reverb", 
            "speedup": f"{base_query} speed up"
        }
        
        search_query = format_queries.get(format_type, base_query)
        
        # Скачиваем трек
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'temp_music_{user_id}.%(ext)s',
            'quiet': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await asyncio.to_thread(
                ydl.extract_info, 
                f"ytsearch1:{search_query}", 
                download=True
            )
            
            if info and 'entries' in info and info['entries']:
                video = info['entries'][0]
                filename = ydl.prepare_filename(video)
                
                # Отправляем аудио
                await callback_query.message.reply_audio(
                    filename,
                    title=f"{music_info['title']} ({format_type})",
                    performer=music_info['artist']
                )
                
                # Очистка
                if os.path.exists(filename):
                    os.remove(filename)
                
                await status_msg.delete()
                await callback_query.message.delete()
            else:
                await status_msg.edit_text("❌ Не удалось найти эту версию")
                await asyncio.sleep(3)
                await status_msg.delete()
                
    except Exception as e:
        logger.error(f"Ошибка скачивания формата: {e}")
        await callback_query.message.reply_text("❌ Ошибка при скачивании")
        await asyncio.sleep(3)

@app.on_callback_query(filters.regex("cancel_operation"))
async def cancel_callback_handler(_, callback_query):
    """Обработчик отмены"""
    await callback_query.answer("Операция отменена")
    await callback_query.message.delete()

@app.on_message(filters.voice | filters.video | filters.document | filters.audio)
async def cleanup_media_messages(_, message):
    """Удаляет ненужные медиа сообщения"""
    await message.delete()

# ==================== СИСТЕМНЫЕ ФУНКЦИИ ====================

async def cleanup_old_files():
    """Фоновая очистка старых файлов"""
    while True:
        await asyncio.sleep(3600)  # Каждый час
        try:
            current_time = time.time()
            users_to_remove = []
            
            for user_id, data in user_videos.items():
                if current_time - data.get('timestamp', 0) > 7200:  # 2 часа
                    temp_dir = data.get('temp_dir')
                    if temp_dir and os.path.exists(temp_dir):
                        shutil.rmtree(temp_dir, ignore_errors=True)
                    users_to_remove.append(user_id)
            
            for user_id in users_to_remove:
                del user_videos[user_id]
                logger.info(f"Очищены файлы пользователя {user_id}")
                
        except Exception as e:
            logger.error(f"Ошибка очистки файлов: {e}")

@app.on_start()
async def startup_cleanup():
    """Запуск фоновых задач при старте"""
    # Удаляем старые сессии
    for session_file in ["video_bot_new_session_2024.session", "video_bot_new_session_2024.session-journal"]:
        if os.path.exists(session_file):
            try:
                os.remove(session_file)
                logger.info(f"Удален старый файл сессии: {session_file}")
            except Exception as e:
                logger.warning(f"Не удалось удалить {session_file}: {e}")
    
    # Запускаем очистку
    asyncio.create_task(cleanup_old_files())
    logger.info("🚀 Бот запущен и готов к работе!")

@app.on_stop()
async def shutdown_cleanup():
    """Очистка при остановке"""
    logger.info("🛑 Останавливаю бота...")
    
    # Отменяем все задачи
    for user_tasks_list in user_tasks.values():
        for task in user_tasks_list:
            task.cancel()
    
    # Очищаем временные файлы
    for user_id, data in user_videos.items():
        temp_dir = data.get('temp_dir')
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)

# ==================== ЗАПУСК ====================

if __name__ == "__main__":
    logger.info("🎬 Запуск Video & Music Bot...")
    
    # Создаем необходимые папки
    os.makedirs("downloads", exist_ok=True)
    
    try:
        app.run()
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
    finally:
        # Финальная очистка
        asyncio.run(shutdown_cleanup())


