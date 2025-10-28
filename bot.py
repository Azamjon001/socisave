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
from pyrogram.types import InputMediaPhoto

API_ID = 26670278
API_HASH = "e3d77390fd9c22d98bb6bddca86fef1a"
BOT_TOKEN = "6788128988:AAEMmCSafiiEqtS5UWQQxfo--W0On7B6Q08"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------------- ФУНКЦИЯ АВТОМАТИЧЕСКОЙ ПЕРЕЗАГРУЗКИ -------------------------
def schedule_restart():
    """Планировщик перезагрузки каждые 12 часов"""
    def restart_job():
        logger.info("🔄 Запланированная перезагрузка бота через 12 часов...")
        os._exit(0)  # Безопасный выход для перезагрузки в Railway
    
    schedule.every(12).hours.do(restart_job)
    
    def run_scheduler():
        while True:
            schedule.run_pending()
            time.sleep(60)  # Проверка каждую минуту
    
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    logger.info("⏰ Планировщик перезагрузки запущен (каждые 12 часов)")

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

def get_instagram_media_info(url: str):
    """Определяем тип контента Instagram (видео/фото) и получаем информацию"""
    if not check_cookies_file():
        raise FileNotFoundError("Файл cookies.txt не найден. Instagram недоступен.")
    
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "cookiefile": "cookies.txt",
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Определяем тип контента
            media_type = "video" if info.get('url') and 'video' in info.get('ext', '') else "photo"
            
            # Для фото может быть несколько изображений
            if media_type == "photo" and 'url' in info:
                photo_urls = [info['url']]
            else:
                photo_urls = []
            
            return {
                'type': media_type,
                'url': info.get('url'),  # Прямая ссылка для видео
                'title': info.get('title', 'Instagram Media'),
                'photo_urls': photo_urls,
                'duration': info.get('duration'),
                'width': info.get('width'),
                'height': info.get('height')
            }
    except Exception as e:
        logger.error(f"Ошибка получения информации Instagram: {e}")
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
        logger.error(f"Ошибка скачивания Instagram видео: {e}")
        raise

def download_instagram_photos(url: str, out_path: str) -> list:
    """Скачиваем Instagram фото"""
    if not check_cookies_file():
        raise FileNotFoundError("Файл cookies.txt не найден.")
    
    ydl_opts = {
        "outtmpl": os.path.join(out_path, "%(title).50s.%(ext)s"),
        "format": "best",
        "cookiefile": "cookies.txt",
        "quiet": True,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            # Если это одно фото
            if hasattr(info, 'url'):
                return [ydl.prepare_filename(info)]
            # Если несколько фото
            elif 'entries' in info:
                return [ydl.prepare_filename(entry) for entry in info['entries']]
            else:
                return [ydl.prepare_filename(info)]
    except Exception as e:
        logger.error(f"Ошибка скачивания Instagram фото: {e}")
        raise

# ------------------------- ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ДЛЯ ОЧИСТКИ -------------------------
user_processing = {}  # Храним статус обработки для каждого пользователя

async def cleanup_user_message(message, delay: int = 3):
    """Удаляет сообщение пользователя после задержки"""
    try:
        await asyncio.sleep(delay)
        await message.delete()
        logger.info(f"🗑️ Удалено сообщение пользователя {message.from_user.id}")
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение: {e}")

# ------------------------- ИСПРАВЛЕННЫЕ ХЭНДЛЕРЫ -------------------------

@app.on_message(filters.command("start"))
async def start(_, message):
    """Обработчик команды /start"""
    welcome_msg = await message.reply_text(
        "Привет! 👋\n\n"
        "📥 Отправь ссылку на Instagram — я скачаю видео или фото для тебя.\n"
        "🎥 Или ссылку на YouTube — тоже скачаю видео.\n\n"
        "⚡ Бот автоматически удалит твою ссылку после скачивания!"
    )

@app.on_message(filters.command(["help", "info"]))
async def help_command(_, message):
    """Обработчик других команд"""
    help_text = (
        "🤖 **Помощь по боту**\n\n"
        "📥 Просто отправь ссылку на:\n"
        "• Instagram видео/реельс/фото\n" 
        "• YouTube видео\n\n"
        "📌 Бот автоматически удалит твою ссылку после скачивания\n"
        "⚡ Скачивание работает быстро и бесплатно!\n"
        "🔄 Бот автоматически перезагружается каждые 12 часов"
    )
    await message.reply_text(help_text)

@app.on_message(filters.text & filters.private)
async def handle_text(_, message):
    """Обработчик текстовых сообщений от пользователей - ТОЛЬКО ДЛЯ ССЫЛОК"""
    
    # Пропускаем команды (они обрабатываются отдельно)
    if message.text and message.text.startswith('/'):
        return
    
    user_id = message.from_user.id
    text = message.text.strip()
    
    # Извлекаем URL
    url = extract_first_url(text)
    if not url or not any(d in url for d in ["youtube.com", "youtu.be", "instagram.com"]):
        # НЕ удаляем обычные текстовые сообщения, только ссылки
        return

    # Проверяем, не обрабатывается ли уже запрос от этого пользователя
    if user_id in user_processing and user_processing[user_id].get('processing'):
        temp_msg = await message.reply_text("⏳ Ваш предыдущий запрос еще обрабатывается...")
        await asyncio.sleep(3)
        await temp_msg.delete()
        return

    # Помечаем как обрабатываемое
    user_processing[user_id] = {'processing': True}
    
    status = None
    
    try:
        url = normalize_url(url)
        status = await message.reply_text("⏳ Обработка контента...")
        
        if "youtube" in url or "youtu.be" in url:
            # YouTube обработка - ТОЛЬКО ВИДЕО
            try:
                # Пытаемся отправить прямую ссылку
                direct_url = await asyncio.to_thread(get_youtube_direct_url, url)
                await message.reply_video(
                    direct_url, 
                    caption="📥 YouTube видео скачано через @azams_bot"
                )
                logger.info("✅ YouTube видео отправлено через прямую ссылку")
                
            except Exception as e:
                # Если прямая ссылка не работает, скачиваем файл
                await status.edit_text("📥 Скачиваю видео...")
                tmp_dir = tempfile.mkdtemp()
                
                try:
                    file_path = await asyncio.to_thread(download_youtube_video, url, tmp_dir)
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
                    # Очистка при ошибке
                    if os.path.exists(tmp_dir):
                        for file in os.listdir(tmp_dir):
                            os.remove(os.path.join(tmp_dir, file))
                        os.rmdir(tmp_dir)
                    raise download_error
                
        elif "instagram.com" in url:
            # Instagram обработка - ОПРЕДЕЛЯЕМ ТИП КОНТЕНТА
            if not os.path.exists("cookies.txt"):
                await status.edit_text("❌ Файл cookies.txt не найден. Instagram недоступен.")
                await asyncio.sleep(5)
                await status.delete()
                return
                
            try:
                # Сначала определяем тип контента
                await status.edit_text("🔍 Определяю тип контента...")
                media_info = await asyncio.to_thread(get_instagram_media_info, url)
                
                if media_info['type'] == 'video':
                    # ОБРАБОТКА ВИДЕО
                    await status.edit_text("🎥 Обрабатываю видео...")
                    try:
                        # Пытаемся получить прямую ссылку
                        if media_info.get('url'):
                            await message.reply_video(
                                media_info['url'], 
                                caption="📥 Instagram видео скачано через @azams_bot"
                            )
                            logger.info("✅ Instagram видео отправлено через прямую ссылку")
                        else:
                            raise Exception("Не удалось получить прямую ссылку")
                        
                    except Exception as e:
                        logger.warning(f"Прямая ссылка не сработала: {e}, скачиваю файл...")
                        await status.edit_text("📥 Скачиваю видео...")
                        tmp_dir = tempfile.mkdtemp()
                        
                        try:
                            file_path = await asyncio.to_thread(download_instagram_video, url, tmp_dir)
                            await message.reply_video(
                                file_path,
                                caption="📥 Instagram видео скачано через @azams_bot"
                            )
                            logger.info("✅ Instagram видео отправлено как файл")
                            
                            # Очистка временных файлов
                            if os.path.exists(file_path):
                                os.remove(file_path)
                            os.rmdir(tmp_dir)
                            
                        except Exception as download_error:
                            # Очистка при ошибке
                            if os.path.exists(tmp_dir):
                                for file in os.listdir(tmp_dir):
                                    os.remove(os.path.join(tmp_dir, file))
                                os.rmdir(tmp_dir)
                            raise download_error
                
                elif media_info['type'] == 'photo':
                    # ОБРАБОТКА ФОТО
                    await status.edit_text("🖼️ Обрабатываю фото...")
                    tmp_dir = tempfile.mkdtemp()
                    
                    try:
                        # Скачиваем фото
                        photo_paths = await asyncio.to_thread(download_instagram_photos, url, tmp_dir)
                        
                        if len(photo_paths) == 1:
                            # Одно фото
                            await message.reply_photo(
                                photo_paths[0],
                                caption="📸 Instagram фото скачано через @azams_bot"
                            )
                            logger.info("✅ Instagram фото отправлено")
                        else:
                            # Несколько фото (альбом)
                            media_group = []
                            for i, photo_path in enumerate(photo_paths):
                                if i == 0:
                                    media_group.append(InputMediaPhoto(
                                        photo_path, 
                                        caption="📸 Instagram фото скачано через @azams_bot"
                                    ))
                                else:
                                    media_group.append(InputMediaPhoto(photo_path))
                            
                            await message.reply_media_group(media_group)
                            logger.info(f"✅ Instagram альбом отправлен ({len(photo_paths)} фото)")
                        
                        # Очистка временных файлов
                        for photo_path in photo_paths:
                            if os.path.exists(photo_path):
                                os.remove(photo_path)
                        os.rmdir(tmp_dir)
                        
                    except Exception as download_error:
                        # Очистка при ошибке
                        if os.path.exists(tmp_dir):
                            for file in os.listdir(tmp_dir):
                                os.remove(os.path.join(tmp_dir, file))
                            os.rmdir(tmp_dir)
                        raise download_error

        # УСПЕШНОЕ ЗАВЕРШЕНИЕ - удаляем только сообщение пользователя со ссылкой
        await message.delete()
        logger.info(f"✅ Обработка завершена для пользователя {user_id}")

    except Exception as e:
        logger.error(f"❌ Ошибка обработки для пользователя {user_id}: {e}")
        
        if status:
            try:
                error_msg = await message.reply_text(f"❌ Ошибка: {str(e)}")
                await asyncio.sleep(5)
                await error_msg.delete()
            except Exception as delete_error:
                logger.warning(f"Не удалось удалить сообщение об ошибке: {delete_error}")
                
    finally:
        # Удаляем статус сообщение
        if status:
            try:
                await status.delete()
            except Exception as delete_error:
                logger.warning(f"Не удалось удалить статус сообщение: {delete_error}")
                
        # Снимаем блокировку обработки
        if user_id in user_processing:
            user_processing[user_id]['processing'] = False


# ------------------------- ЗАПУСК -------------------------
if __name__ == "__main__":
    # Запускаем планировщик перезагрузки
    schedule_restart()
    
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
    
    logger.info("🚀 Запуск бота с исправленной логикой...")
    logger.info("📝 Бот будет удалять ТОЛЬКО ссылки после скачивания, остальные сообщения остаются")
    logger.info("🔄 Автоматическая перезагрузка каждые 12 часов активирована")
    app.run()


