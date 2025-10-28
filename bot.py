import os
import asyncio
import logging
import tempfile
import yt_dlp
import re
import random
import time
import requests
import schedule
import threading
from pyrogram import Client, filters
from pyrogram.errors import BadRequest, BadMsgNotification

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

# ------------------------- вспомогательные функции -------------------------
def extract_first_url(text: str) -> str:
    match = re.search(r"(https?://[^\s]+)", text)
    return match.group(1) if match else ""

def normalize_url(url: str) -> str:
    if "youtu.be/" in url:
        video_id = url.split("/")[-1].split("?")[0]
        return f"https://www.youtube.com/watch?v={video_id}"
    return url

# ✅ ИСПРАВЛЕНО: YouTube функции
def get_youtube_direct_url(url: str) -> str:
    """Получаем прямую ссылку на YouTube видео"""
    ydl_opts = {
        "quiet": True, 
        "skip_download": True, 
        "format": "best[height<=720][ext=mp4]/best[ext=mp4]/best",
        "noplaylist": True
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            # Ищем подходящий формат
            if 'url' in info:
                return info['url']
            elif 'formats' in info:
                # Выбираем лучший mp4 формат
                formats = [f for f in info['formats'] if f.get('ext') == 'mp4' and f.get('height', 0) <= 720]
                if formats:
                    best_format = max(formats, key=lambda x: x.get('height', 0))
                    return best_format['url']
            raise Exception("Не удалось найти подходящую ссылку")
    except Exception as e:
        logger.error(f"Ошибка получения YouTube URL: {e}")
        raise

def download_youtube_video(url: str, out_path: str) -> str:
    """Скачиваем YouTube видео"""
    ydl_opts = {
        "outtmpl": os.path.join(out_path, "%(title).50s.%(ext)s"),
        "format": "best[height<=720][ext=mp4]/best[ext=mp4]/best",
        "noplaylist": True,
        "quiet": False,  # Включаем логи для отладки
        "retries": 3,
        "merge_output_format": "mp4",
        "concurrent_fragment_downloads": 4,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            logger.info(f"✅ YouTube видео скачано: {filename}")
            return filename
    except Exception as e:
        logger.error(f"❌ Ошибка скачивания YouTube: {e}")
        raise

# ✅ Instagram функции с правильным использованием cookies
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
        # Оставляем только последние 500 записей
        processed_messages = set(list(processed_messages)[-500:])
        logger.info("🧹 Очищены старые записи из processed_messages")

# ------------------------- АВТОМАТИЧЕСКИЙ ПЕРЕЗАПУСК -------------------------
def schedule_restart():
    """Планировщик для автоматического перезапуска каждые 12 часов"""
    def restart_job():
        logger.info("🔄 Запланированный перезапуск бота...")
        os._exit(0)  # Завершаем процесс для перезапуска
    
    # Настраиваем перезапуск каждые 12 часов
    schedule.every(12).hours.do(restart_job)
    
    def run_scheduler():
        while True:
            schedule.run_pending()
            time.sleep(60)  # Проверяем каждую минуту
    
    # Запускаем планировщик в отдельном потоке
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    logger.info("⏰ Планировщик перезапуска запущен (каждые 12 часов)")

# ------------------------- ИСПРАВЛЕННЫЕ ХЭНДЛЕРЫ -------------------------

@app.on_message(filters.command("start"))
async def start(_, message):
    """Обработчик команды /start"""
    message_id = f"start_{message.id}_{message.from_user.id}"
    
    if message_id in processed_messages:
        return
        
    processed_messages.add(message_id)
    
    welcome_msg = await message.reply_text(
        "Привет! 👋\n\n"
        "📥 Отправь ссылку на Instagram — я скачаю видео для тебя.\n"
        "🎥 Или ссылку на YouTube — тоже скачаю видео.\n\n"
        "⚡ Бот автоматически удалит твою ссылку после скачивания!"
    )
    
    cleanup_old_processed_messages()

@app.on_message(filters.command(["help", "info"]))
async def help_command(_, message):
    """Обработчик других команд"""
    message_id = f"help_{message.id}_{message.from_user.id}"
    
    if message_id in processed_messages:
        return
        
    processed_messages.add(message_id)
    
    help_text = (
        "🤖 **Помощь по боту**\n\n"
        "📥 Просто отправь ссылку на:\n"
        "• Instagram видео/реельс\n" 
        "• YouTube видео\n\n"
        "📌 Бот автоматически удалит твою ссылку после скачивания\n"
        "⚡ Скачивание работает быстро и бесплатно!"
    )
    await message.reply_text(help_text)
    
    cleanup_old_processed_messages()

@app.on_message(filters.text & filters.private)
async def handle_text(_, message):
    """Обработчик текстовых сообщений от пользователей"""
    
    message_id = f"text_{message.id}_{message.from_user.id}"
    
    if message_id in processed_messages:
        return
        
    if message.text and message.text.startswith('/'):
        return
    
    user_id = message.from_user.id
    text = message.text.strip()
    
    url = extract_first_url(text)
    if not url or not any(d in url for d in ["youtube.com", "youtu.be", "instagram.com"]):
        return

    processed_messages.add(message_id)
    
    if user_id in user_processing and user_processing[user_id].get('processing'):
        temp_msg = await message.reply_text("⏳ Ваш предыдущий запрос еще обрабатывается...")
        await asyncio.sleep(3)
        await temp_msg.delete()
        processed_messages.discard(message_id)
        return

    user_processing[user_id] = {'processing': True}
    
    status = None
    
    try:
        url = normalize_url(url)
        status = await message.reply_text("⏳ Обработка видео...")
        
        if "youtube" in url or "youtu.be" in url:
            # YouTube обработка - ИСПРАВЛЕННАЯ
            try:
                await status.edit_text("🔗 Получаю прямую ссылку YouTube...")
                direct_url = await asyncio.to_thread(get_youtube_direct_url, url)
                
                if direct_url:
                    await status.edit_text("📤 Отправляю видео...")
                    await message.reply_video(
                        direct_url, 
                        caption="📥 YouTube видео скачано через @azams_bot"
                    )
                    logger.info("✅ YouTube видео отправлено через прямую ссылку")
                else:
                    raise Exception("Не удалось получить прямую ссылку")
                
            except Exception as e:
                logger.warning(f"Прямая ссылка YouTube не сработала: {e}, скачиваю файл...")
                await status.edit_text("📥 Скачиваю YouTube видео...")
                tmp_dir = tempfile.mkdtemp()
                
                try:
                    file_path = await asyncio.to_thread(download_youtube_video, url, tmp_dir)
                    await status.edit_text("📤 Отправляю видео...")
                    await message.reply_video(
                        file_path, 
                        caption="📥 YouTube видео скачано через @azams_bot"
                    )
                    logger.info("✅ YouTube видео отправлено как файл")
                    
                    # Очистка временных файлов
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    os.rmdir(tmp_dir)
                    
                except Exception as download_error:
                    if os.path.exists(tmp_dir):
                        for file in os.listdir(tmp_dir):
                            os.remove(os.path.join(tmp_dir, file))
                        os.rmdir(tmp_dir)
                    raise download_error
                
        elif "instagram.com" in url:
            # Instagram обработка
            if not os.path.exists("cookies.txt"):
                await status.edit_text("❌ Файл cookies.txt не найден. Instagram недоступен.")
                await asyncio.sleep(5)
                await status.delete()
                return
                
            try:
                await status.edit_text("🔗 Получаю прямую ссылку Instagram...")
                direct_url = await asyncio.to_thread(get_instagram_url, url)
                if direct_url:
                    await status.edit_text("📤 Отправляю видео...")
                    await message.reply_video(
                        direct_url, 
                        caption="📥 Instagram видео скачано через @azams_bot"
                    )
                    logger.info("✅ Instagram видео отправлено через прямую ссылку")
                else:
                    raise Exception("Не удалось получить прямую ссылку")
                
            except Exception as e:
                logger.warning(f"Прямая ссылка Instagram не сработала: {e}, скачиваю файл...")
                await status.edit_text("📥 Скачиваю Instagram видео...")
                tmp_dir = tempfile.mkdtemp()
                
                try:
                    file_path = await asyncio.to_thread(download_instagram_video, url, tmp_dir)
                    await status.edit_text("📤 Отправляю видео...")
                    await message.reply_video(
                        file_path,
                        caption="📥 Instagram видео скачано через @azams_bot"
                    )
                    logger.info("✅ Instagram видео отправлено как файл")
                    
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    os.rmdir(tmp_dir)
                    
                except Exception as download_error:
                    if os.path.exists(tmp_dir):
                        for file in os.listdir(tmp_dir):
                            os.remove(os.path.join(tmp_dir, file))
                        os.rmdir(tmp_dir)
                    raise download_error

        # Успешное завершение
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
        if status:
            try:
                await status.delete()
            except:
                pass
                
        if user_id in user_processing:
            user_processing[user_id]['processing'] = False
            
        cleanup_old_processed_messages()

# ------------------------- ЗАПУСК -------------------------
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
    
    # Запускаем планировщик перезапуска
    schedule_restart()
    
    logger.info("🚀 Запуск бота с исправленным YouTube и автоматическим перезапуском...")
    logger.info("⏰ Бот будет автоматически перезапускаться каждые 12 часов")
    
    try:
        app.run()
    except Exception as e:
        logger.error(f"❌ Ошибка запуска бота: {e}")
        # Ждем немного перед завершением
        time.sleep(5)
        os._exit(1)

