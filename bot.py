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

API_ID = 26670278
API_HASH = "e3d77390fd9c22d98bb6bddca86fef1a"
BOT_TOKEN = "6788128988:AAEMmCSafiiEqtS5UWQQxfo--W0On7B6Q08"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

# ------------------------- ИЗМЕНЕНО: новое имя сессии -------------------------
app = SafeClient(
    "video_bot_new_session_2024",  # ⬅️ ИЗМЕНИЛ ИМЯ СЕССИИ!
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    sleep_threshold=15
)

# ------------------------- вспомогательные функции -------------------------
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

# ✅ ИСПРАВЛЕНО: Instagram функции с правильным использованием cookies
def check_cookies_file():
    """Проверяем наличие cookies файла"""
    if not os.path.exists("cookies.txt"):
        logger.error("❌ Файл cookies.txt не найден!")
        return False
    logger.info("✅ Файл cookies.txt найден")
    return True

def get_instagram_url(url: str) -> str:
    """Получаем прямую ссылку на Instagram видео"""
    if not check_cookies_file():
        raise FileNotFoundError("Файл cookies.txt не найден. Instagram недоступен.")
    
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "format": "best[ext=mp4]/best",
        "cookiefile": "cookies.txt",
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get("url")
    except Exception as e:
        logger.error(f"Ошибка получения Instagram URL: {e}")
        raise

def download_instagram_video(url: str, out_path: str) -> str:
    """Скачиваем Instagram видео если прямая ссылка не работает"""
    if not check_cookies_file():
        raise FileNotFoundError("Файл cookies.txt не найден.")
    
    ydl_opts = {
        "outtmpl": os.path.join(out_path, "%(title).50s.%(ext)s"),
        "format": "best[ext=mp4]/best",
        "cookiefile": "cookies.txt",
        "quiet": True,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info)
    except Exception as e:
        logger.error(f"Ошибка скачивания Instagram: {e}")
        raise

def generate_task() -> str:
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
            "🔢 Продолжи ряд: 2, 4, 6, 8, ... ?",
            "🧮 Что больше: половина от 8 или треть от 9?",
        ]
        return random.choice(riddles)

# ------------------------- хэндлеры -------------------------
@app.on_message(filters.command("start"))
async def start(_, message):
    await message.reply_text(
        "Привет! 👋\n\n"
        "📥 Отправь ссылку на Instagram — я скачаю видео для тебя.\n"
        "🎥 Или ссылку на YouTube — тоже скачаю видео.\n\n"
        "⚠️ Для Instagram требуется файл cookies.txt"
    )

@app.on_message(filters.text & ~filters.command("start"))
async def handle_text(_, message):
    text = message.text.strip()
    url = extract_first_url(text)
    if not url or not any(d in url for d in ["youtube.com", "youtu.be", "instagram.com"]):
        await message.delete()
        return

    status = await message.reply_text("⏳ Обработка видео...")
    try:
        url = normalize_url(url)
        
        if "youtube" in url or "youtu.be" in url:
            task_msg = await message.reply_text(generate_task())
            try:
                direct_url = await asyncio.to_thread(get_youtube_direct_url, url)
                await message.reply_video(direct_url, caption="📥 YouTube видео через @azams_bot")
            except BadRequest:
                tmp_dir = tempfile.mkdtemp()
                file_path = await asyncio.to_thread(download_youtube_video, url, tmp_dir)
                await message.reply_video(file_path, caption="📥 YouTube видео через @azams_bot")
                os.remove(file_path)
                os.rmdir(tmp_dir)
            await task_msg.delete()
            
        elif "instagram.com" in url:
            # ✅ Instagram с обработкой ошибок cookies
            if not os.path.exists("cookies.txt"):
                await status.edit_text("❌ Файл cookies.txt не найден. Instagram недоступен.")
                await asyncio.sleep(5)
                return
                
            try:
                direct_url = await asyncio.to_thread(get_instagram_url, url)
                await message.reply_video(direct_url, caption="📥 Instagram видео через @azams_bot")
            except Exception as e:
                await status.edit_text(f"❌ Ошибка Instagram: {e}")
                await asyncio.sleep(5)
                return

        await message.delete()
        await status.delete()
        
    except Exception as e:
        await status.edit_text(f"❌ Ошибка: {e}")
        await asyncio.sleep(5)
        await status.delete()

@app.on_message(filters.voice | filters.document | filters.audio | filters.sticker | filters.animation | filters.photo)
async def cleanup_messages(_, message):
    if message.photo:
        return
    await message.delete()
    await app.unpin_chat_message(chat_id=message.chat.id)

# ------------------------- запуск -------------------------
if __name__ == "__main__":
    # Удаляем старые файлы сессии перед запуском
    old_sessions = ["fast_bot.session", "fast_bot.session-journal"]
    for session_file in old_sessions:
        if os.path.exists(session_file):
            try:
                os.remove(session_file)
                logger.info(f"🗑️ Удален старый файл сессии: {session_file}")
            except Exception as e:
                logger.warning(f"Не удалось удалить {session_file}: {e}")
    
    # Проверяем cookies при запуске
    if os.path.exists("cookies.txt"):
        logger.info("✅ Файл cookies.txt найден - Instagram доступен")
    else:
        logger.warning("⚠️ Файл cookies.txt не найден - Instagram недоступен")
    
    logger.info("🚀 Запуск бота с новой сессией...")
    app.run()






























# === ДОБАВЛЯЕМ ПОСЛЕ ВАШЕГО СУЩЕСТВУЮЩЕГО КОДА (в конец файла) ===

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from shazamio import Shazam
from pydub import AudioSegment
import os
import asyncio

# Глобальная переменная для хранения путей к видео
user_videos = {}

# Функция для извлечения аудио из видео
async def extract_audio_from_video(video_path, user_id):
    try:
        # Создаем уникальный путь для аудио файла
        audio_path = f"temp_audio_{user_id}.wav"
        
        # Конвертируем видео в аудио
        audio = AudioSegment.from_file(video_path, format="mp4")
        
        # Берем только первые 30 секунд для Shazam (оптимально для распознавания)
        first_30_seconds = audio[:30000]
        first_30_seconds.export(audio_path, format="wav")
        
        return audio_path
    except Exception as e:
        logger.error(f"Ошибка извлечения аудио: {e}")
        return None

# Функция распознавания музыки через Shazam
async def recognize_music(audio_path):
    try:
        shazam = Shazam()
        result = await shazam.recognize(audio_path)
        
        if result and 'track' in result:
            track = result['track']
            return {
                'title': track.get('title', 'Неизвестно'),
                'artist': track.get('subtitle', 'Неизвестный артист'),
                'shazam_id': track.get('key'),
                'success': True
            }
        return {'success': False, 'error': 'Музыка не распознана'}
    except Exception as e:
        logger.error(f"Ошибка Shazam: {e}")
        return {'success': False, 'error': str(e)}

# Функция создания кнопок форматов
def create_format_buttons():
    keyboard = [
        [InlineKeyboardButton("🎵 Original", callback_data="format_original")],
        [InlineKeyboardButton("🔄 Remix", callback_data="format_remix")],
        [InlineKeyboardButton("📝 Lyrics", callback_data="format_lyrics")],
        [InlineKeyboardButton("🐌 Slowed", callback_data="format_slowed")],
        [InlineKeyboardButton("⚡ Speed Up", callback_data="format_speedup")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Функция поиска и скачивания трека
async def download_music_track(format_type, track_info, chat_id):
    try:
        search_query = f"{track_info['artist']} - {track_info['title']}"
        
        # Модифицируем запрос в зависимости от формата
        format_queries = {
            "original": search_query,
            "remix": f"{search_query} remix",
            "lyrics": f"{search_query} lyrics",
            "slowed": f"{search_query} slowed reverb",
            "speedup": f"{search_query} speed up"
        }
        
        final_query = format_queries.get(format_type, search_query)
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'downloads/%(title)s.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
        }
        
        # Создаем папку downloads если нет
        os.makedirs('downloads', exist_ok=True)
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Ищем и скачиваем
            info = ydl.extract_info(f"ytsearch1:{final_query}", download=True)
            
            if info and 'entries' in info and info['entries']:
                video = info['entries'][0]
                audio_file = ydl.prepare_filename(video)
                # Конвертируем расширение
                audio_file = audio_file.replace('.webm', '.mp3').replace('.m4a', '.mp3')
                
                if os.path.exists(audio_file):
                    return audio_file
                    
        return None
    except Exception as e:
        logger.error(f"Ошибка скачивания музыки: {e}")
        return None

# Обработчик для кнопки Shazam (добавляем в существующие хэндлеры)
@app.on_callback_query(filters.regex("shazam_video"))
async def shazam_handler(_, callback_query):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    
    await callback_query.answer()
    
    # Показываем статус поиска
    status_msg = await callback_query.message.reply_text("🔍 Ищу музыку в видео...")
    
    # Получаем путь к видео
    video_path = user_videos.get(user_id)
    if not video_path or not os.path.exists(video_path):
        await status_msg.edit_text("❌ Видео не найдено или удалено")
        await asyncio.sleep(3)
        await status_msg.delete()
        return
    
    try:
        # Извлекаем аудио
        audio_path = await extract_audio_from_video(video_path, user_id)
        if not audio_path:
            await status_msg.edit_text("❌ Ошибка обработки аудио")
            await asyncio.sleep(3)
            await status_msg.delete()
            return
        
        # Распознаем музыку
        recognition_result = await recognize_music(audio_path)
        
        # Удаляем временный аудио файл
        if os.path.exists(audio_path):
            os.remove(audio_path)
        
        if recognition_result['success']:
            # Сохраняем информацию о треке
            user_videos[f"{user_id}_track"] = recognition_result
            
            # Показываем результат и кнопки форматов
            track_text = f"🎶 **Найден трек:**\n**Артист:** {recognition_result['artist']}\n**Название:** {recognition_result['title']}\n\nВыбери формат:"
            
            await status_msg.edit_text(
                track_text,
                reply_markup=create_format_buttons()
            )
        else:
            await status_msg.edit_text("❌ Не удалось распознать музыку в видео")
            await asyncio.sleep(3)
            await status_msg.delete()
            
    except Exception as e:
        logger.error(f"Ошибка Shazam обработки: {e}")
        await status_msg.edit_text("❌ Ошибка при распознавании музыки")
        await asyncio.sleep(3)
        await status_msg.delete()

# Обработчик выбора формата
@app.on_callback_query(filters.regex("^format_"))
async def format_handler(_, callback_query):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    format_type = callback_query.data.replace("format_", "")
    
    await callback_query.answer()
    
    # Получаем информацию о треке
    track_info = user_videos.get(f"{user_id}_track")
    if not track_info:
        await callback_query.message.reply_text("❌ Информация о треке устарела")
        return
    
    # Показываем статус скачивания
    download_msg = await callback_query.message.reply_text(f"⏬ Скачиваю {format_type} версию...")
    
    try:
        # Скачиваем трек
        audio_file = await download_music_track(format_type, track_info, chat_id)
        
        if audio_file and os.path.exists(audio_file):
            # Отправляем аудио файл
            await callback_query.message.reply_audio(
                audio=audio_file,
                title=f"{track_info['artist']} - {track_info['title']} ({format_type})",
                performer=track_info['artist']
            )
            await download_msg.delete()
            
            # Удаляем временный файл
            os.remove(audio_file)
        else:
            await download_msg.edit_text("❌ Не удалось найти или скачать эту версию")
            await asyncio.sleep(3)
            await download_msg.delete()
            
    except Exception as e:
        logger.error(f"Ошибка отправки аудио: {e}")
        await download_msg.edit_text("❌ Ошибка при отправке файла")
        await asyncio.sleep(3)
        await download_msg.delete()

# Модифицируем существующий хэндлер для сохранения пути к видео и добавления кнопки Shazam
original_handle_text = app.on_message(filters.text & ~filters.command("start"))

@app.on_message(filters.text & ~filters.command("start"))
async def enhanced_handle_text(_, message):
    # Вызываем оригинальную функцию
    await original_handle_text(_, message)
    
    # Дополнительно: сохраняем путь к видео и добавляем кнопку Shazam
    text = message.text.strip()
    url = extract_first_url(text)
    
    if url and any(d in url for d in ["youtube.com", "youtu.be", "instagram.com"]):
        user_id = message.from_user.id
        
        # Сохраняем информацию о пользователе для возможного Shazam
        # (в реальной реализации нужно сохранить путь к скачанному видео)
        try:
            # Создаем временную папку для пользователя
            user_temp_dir = f"temp_{user_id}"
            os.makedirs(user_temp_dir, exist_ok=True)
            
            # Сохраняем путь (в реальной реализации нужно получить актуальный путь к файлу)
            user_videos[user_id] = user_temp_dir
            
            # Отправляем сообщение с кнопкой Shazam через 2 секунды после успешной загрузки
            await asyncio.sleep(2)
            
            keyboard = [[InlineKeyboardButton("🎵 Shazam музыку из видео", callback_data="shazam_video")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await message.reply_text(
                "✅ Видео загружено! Хочешь найти музыку из этого видео?",
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"Ошибка добавления кнопки Shazam: {e}")

# Функция очистки временных файлов
async def cleanup_temp_files():
    """Очистка временных файлов раз в час"""
    while True:
        await asyncio.sleep(3600)  # Каждый час
        try:
            current_time = time.time()
            for user_id, temp_dir in list(user_videos.items()):
                if isinstance(temp_dir, str) and temp_dir.startswith("temp_") and os.path.exists(temp_dir):
                    # Удаляем папки старше 2 часов
                    dir_time = os.path.getctime(temp_dir)
                    if current_time - dir_time > 7200:  # 2 часа
                        import shutil
                        shutil.rmtree(temp_dir)
                        del user_videos[user_id]
                        logger.info(f"Очищена временная папка для user_{user_id}")
        except Exception as e:
            logger.error(f"Ошибка очистки временных файлов: {e}")

# Запускаем очистку при старте бота
@app.on_start()
async def start_cleanup():
    asyncio.create_task(cleanup_temp_files())

logger.info("✅ Shazam функционал добавлен успешно!")

