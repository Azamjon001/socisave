import os
import asyncio
import logging
import tempfile
import yt_dlp
import re
import time
import random
import requests
from pyrogram import Client, filters
from pyrogram.errors import BadRequest, BadMsgNotification

API_ID = 26670278
API_HASH = "e3d77390fd9c22d98bb6bddca86fef1a"
BOT_TOKEN = "6788128988:AAEMmCSafiiEqtS5UWQQxfo--W0On7B6Q08"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Глобальные переменные
user_processing = {}
processed_messages = set()

class SafeClient(Client):
    async def send(self, *args, **kwargs):
        for attempt in range(3):
            try:
                return await super().send(*args, **kwargs)
            except BadMsgNotification as e:
                if e.error_code == 16:
                    logger.warning(f"BadMsgNotification [16], попытка {attempt + 1}/3")
                    self.session.msg_id_offset = int(time.time() * 2**32)
                    await asyncio.sleep(1)
                else:
                    raise
        raise RuntimeError("Не удалось синхронизировать msg_id с Telegram")

app = SafeClient(
    "video_bot_new_session_2024",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    sleep_threshold=15
)

# ------------------------- YOUTUBE ФУНКЦИИ -------------------------

def download_youtube_video(url: str, out_path: str) -> str:
    """Скачивание YouTube видео"""
    ydl_opts = {
        "outtmpl": os.path.join(out_path, "%(title).100s.%(ext)s"),
        "format": "best[height<=720]/best",
        "noplaylist": True,
        "quiet": False,
        "ignoreerrors": True,
        "retries": 3,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            if not os.path.exists(filename):
                raise Exception(f"Файл не создан: {filename}")
                
            file_size = os.path.getsize(filename)
            if file_size == 0:
                os.remove(filename)
                raise Exception(f"Файл пустой: {filename}")
                
            logger.info(f"✅ YouTube видео скачано: {filename}")
            return filename
            
    except Exception as e:
        logger.error(f"❌ Ошибка YouTube: {e}")
        raise

# ------------------------- INSTAGRAM АЛЬТЕРНАТИВНЫЕ МЕТОДЫ -------------------------

def check_cookies_file():
    """Проверяем cookies файл"""
    if not os.path.exists("cookies.txt"):
        return False
    
    file_size = os.path.getsize("cookies.txt")
    if file_size == 0:
        return False
        
    return True

def try_instagram_public(url: str, out_path: str):
    """Пробуем скачать через публичные методы (без cookies)"""
    try:
        ydl_opts = {
            "outtmpl": os.path.join(out_path, "instagram_%(title)s.%(ext)s"),
            "quiet": False,
            "ignoreerrors": True,
            "retries": 2,
            "extract_flat": False,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            # Ищем любой скачанный файл
            for file in os.listdir(out_path):
                file_path = os.path.join(out_path, file)
                if os.path.isfile(file_path) and os.path.getsize(file_path) > 0:
                    return file_path, info
            
            raise Exception("Не удалось скачать через публичный метод")
            
    except Exception as e:
        raise Exception(f"Публичный метод не сработал: {e}")

def try_instagram_with_cookies(url: str, out_path: str):
    """Пробуем скачать с cookies"""
    if not check_cookies_file():
        raise Exception("Cookies файл не найден")
    
    try:
        ydl_opts = {
            "outtmpl": os.path.join(out_path, "instagram_%(title)s.%(ext)s"),
            "cookiefile": "cookies.txt",
            "quiet": False,
            "ignoreerrors": True,
            "retries": 3,
            "extract_flat": False,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            # Ищем любой скачанный файл
            for file in os.listdir(out_path):
                file_path = os.path.join(out_path, file)
                if os.path.isfile(file_path) and os.path.getsize(file_path) > 0:
                    return file_path, info
            
            raise Exception("Не удалось скачать даже с cookies")
            
    except Exception as e:
        raise Exception(f"Метод с cookies не сработал: {e}")

def download_instagram_all_methods(url: str, out_path: str):
    """Пробуем все методы скачивания Instagram"""
    methods = [
        ("Публичный метод", try_instagram_public),
        ("Метод с cookies", try_instagram_with_cookies),
    ]
    
    last_error = None
    
    for method_name, method_func in methods:
        try:
            logger.info(f"🔄 Пробую {method_name}...")
            return method_func(url, out_path)
        except Exception as e:
            last_error = e
            logger.warning(f"❌ {method_name} не сработал: {e}")
            time.sleep(2)
            continue
    
    raise Exception(f"Все методы Instagram не сработали. Instagram временно недоступен.")

# ------------------------- INSTAGRAM WEB API ALTERNATIVE -------------------------

def download_instagram_fallback(url: str) -> str:
    """Альтернативный метод через веб-запросы (для публичных постов)"""
    try:
        # Используем сторонний сервис как запасной вариант
        # Это пример - можно добавить реальный API
        service_url = f"https://instasupersave.com/api/ig"
        
        response = requests.post(service_url, json={"url": url}, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success') and data.get('url'):
                # Скачиваем медиа по полученной ссылке
                media_url = data['url']
                response = requests.get(media_url, stream=True, timeout=30)
                
                if response.status_code == 200:
                    # Сохраняем временный файл
                    ext = 'mp4' if 'video' in response.headers.get('content-type', '') else 'jpg'
                    file_path = os.path.join(tempfile.gettempdir(), f"instagram_{int(time.time())}.{ext}")
                    
                    with open(file_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    
                    if os.path.getsize(file_path) > 0:
                        return file_path
                    
                    os.remove(file_path)
                
        raise Exception("Альтернативный метод не сработал")
        
    except Exception as e:
        raise Exception(f"Альтернативный метод ошибка: {e}")

# ------------------------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ -------------------------

def extract_first_url(text: str) -> str:
    match = re.search(r"(https?://[^\s]+)", text)
    return match.group(1) if match else ""

def normalize_url(url: str) -> str:
    if "youtu.be/" in url:
        video_id = url.split("/")[-1].split("?")[0]
        return f"https://www.youtube.com/watch?v={video_id}"
    if "youtube.com/shorts/" in url:
        video_id = url.split("/shorts/")[-1].split("?")[0]
        return f"https://www.youtube.com/watch?v={video_id}"
    return url

def get_media_type(file_path: str) -> str:
    """Определяем тип медиа по расширению файла"""
    if not file_path:
        return "unknown"
    
    ext = file_path.lower().split('.')[-1]
    
    if ext in ['mp4', 'webm', 'mkv', 'mov', 'avi']:
        return "video"
    elif ext in ['jpg', 'jpeg', 'png', 'webp', 'gif']:
        return "photo"
    else:
        return "unknown"

async def safe_send_video(client, chat_id, file_path, caption=""):
    """Безопасная отправка видео"""
    try:
        if not os.path.exists(file_path):
            raise Exception(f"Файл не существует: {file_path}")
            
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            raise Exception(f"Файл пустой: {file_path}")
            
        return await client.send_video(
            chat_id=chat_id,
            video=file_path,
            caption=caption,
            supports_streaming=True
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка отправки видео: {e}")
        raise

async def safe_send_photo(client, chat_id, file_path, caption=""):
    """Безопасная отправка фото"""
    try:
        if not os.path.exists(file_path):
            raise Exception(f"Файл не существует: {file_path}")
            
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            raise Exception(f"Файл пустой: {file_path}")
            
        return await client.send_photo(
            chat_id=chat_id,
            photo=file_path,
            caption=caption
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка отправки фото: {e}")
        raise

# ------------------------- ОБРАБОТЧИКИ -------------------------

@app.on_message(filters.command("start"))
async def start(client, message):
    message_id = f"start_{message.id}_{message.from_user.id}"
    
    if message_id in processed_messages:
        return
        
    processed_messages.add(message_id)
    
    has_cookies = check_cookies_file()
    
    welcome_text = (
        "Привет! 👋\n\n"
        "📥 **YouTube:** ✅ Всегда работает!\n"
        "• Видео, Shorts, музыка\n"
        "• Быстрое скачивание\n\n"
    )
    
    if has_cookies:
        welcome_text += (
            "📸 **Instagram:** ⚠️ Ограниченно\n"
            "• Публичные посты (иногда)\n"
            "• Требуются актуальные cookies\n"
            "• Может не работать из-за ограничений Instagram\n\n"
        )
    else:
        welcome_text += (
            "📸 **Instagram:** ❌ Требует настройки\n"
            "• Нужен файл cookies.txt\n"
            "• Только публичные посты\n"
            "• Часто бывают ограничения\n\n"
        )
    
    welcome_text += (
        "⚡ Просто отправь ссылку!\n"
        "🔄 Бот перезапускается каждые 12 часов"
    )
    
    await message.reply_text(welcome_text)

@app.on_message(filters.command(["help", "info"]))
async def help_command(client, message):
    message_id = f"help_{message.id}_{message.from_user.id}"
    
    if message_id in processed_messages:
        return
        
    processed_messages.add(message_id)
    
    has_cookies = check_cookies_file()
    
    help_text = (
        "🤖 **Помощь по боту**\n\n"
        "🎥 **YouTube (рекомендуется):**\n"
        "• ✅ Видео любой длительности\n"
        "• ✅ YouTube Shorts\n"
        "• ✅ Музыкальные клипы\n"
        "• ✅ Стабильная работа\n\n"
    )
    
    if has_cookies:
        help_text += (
            "📸 **Instagram (ограниченно):**\n"
            "• ⚠️ Только публичные посты\n"
            "• ⚠️ Может не работать\n"
            "• ⚠️ Требует актуальные cookies\n"
            "• ❌ Приватные аккаунты\n"
            "• ❌ Частые ограничения\n\n"
        )
    else:
        help_text += (
            "📸 **Instagram:**\n"
            "• ❌ Требует файл cookies.txt\n"
            "• ❌ Сложная настройка\n"
            "• ❌ Частые ошибки\n\n"
        )
    
    help_text += (
        "💡 **Совет:** Используйте YouTube для надежного скачивания!\n"
        "📝 Просто отправьте ссылку на YouTube видео."
    )
    
    await message.reply_text(help_text)

@app.on_message(filters.command("test"))
async def test_command(client, message):
    """Тестовая команда для проверки ссылок"""
    try:
        text = message.text.split(' ', 1)
        if len(text) < 2:
            await message.reply_text("📝 Использование: /test <ссылка>")
            return
        
        url = text[1].strip()
        
        if "youtube.com" in url or "youtu.be" in url:
            await message.reply_text("✅ YouTube ссылка - должна работать!")
        elif "instagram.com" in url:
            has_cookies = check_cookies_file()
            if has_cookies:
                await message.reply_text("⚠️ Instagram ссылка - может не работать из-за ограничений платформы")
            else:
                await message.reply_text("❌ Instagram ссылка - требуется cookies.txt файл")
        else:
            await message.reply_text("❌ Неподдерживаемая ссылка")
            
    except Exception as e:
        await message.reply_text(f"❌ Ошибка: {e}")

@app.on_message(filters.text & filters.private)
async def handle_text(client, message):
    if message.text.startswith('/'):
        return
    
    message_id = f"text_{message.id}_{message.from_user.id}"
    
    if message_id in processed_messages:
        return
        
    user_id = message.from_user.id
    text = message.text.strip()
    
    url = extract_first_url(text)
    if not url:
        return

    # Проверяем поддерживаемые домены
    supported_domains = ["youtube.com", "youtu.be", "instagram.com"]
    if not any(domain in url for domain in supported_domains):
        await message.reply_text(
            "❌ Неподдерживаемая ссылка\n\n"
            "🎥 **Поддерживается:**\n"
            "• YouTube (youtube.com, youtu.be) - ✅ Рекомендуется\n"
            "• Instagram (instagram.com) - ⚠️ Ограниченно\n\n"
            "💡 Для надежной работы используйте YouTube ссылки"
        )
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
        status = await message.reply_text("⏳ Обработка ссылки...")
        
        if "youtube" in url or "youtu.be" in url:
            # YouTube обработка - ОСНОВНОЙ РАБОЧИЙ МЕТОД
            tmp_dir = tempfile.mkdtemp()
            file_path = None
            
            try:
                await status.edit_text("📥 Скачиваю YouTube видео...")
                file_path = await asyncio.to_thread(download_youtube_video, url, tmp_dir)
                
                await status.edit_text("📤 Отправляю видео...")
                await safe_send_video(
                    client,
                    message.chat.id,
                    file_path,
                    caption="📥 YouTube видео скачано через @azams_bot"
                )
                logger.info("✅ YouTube видео успешно отправлено")

            except Exception as e:
                logger.error(f"❌ YouTube ошибка: {e}")
                raise Exception(f"❌ Не удалось скачать YouTube видео\n\nПричина: {str(e)}")
                
            finally:
                # Очистка
                if file_path and os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except:
                        pass
                if os.path.exists(tmp_dir):
                    try:
                        for file in os.listdir(tmp_dir):
                            os.remove(os.path.join(tmp_dir, file))
                        os.rmdir(tmp_dir)
                    except:
                        pass
                
        elif "instagram.com" in url:
            # Instagram обработка - ЗАПАСНОЙ МЕТОД
            tmp_dir = tempfile.mkdtemp()
            file_path = None
            
            try:
                await status.edit_text("⚠️ Пробую скачать Instagram...")
                
                # Пробуем все методы
                file_path, info = await asyncio.to_thread(download_instagram_all_methods, url, tmp_dir)
                
                if not file_path:
                    raise Exception("Все методы не сработали")
                
                # Определяем тип медиа и отправляем
                media_type = get_media_type(file_path)
                await status.edit_text("📤 Отправляю...")
                
                if media_type == "video":
                    await safe_send_video(
                        client,
                        message.chat.id,
                        file_path,
                        caption="📥 Instagram видео скачано через @azams_bot"
                    )
                else:
                    await safe_send_photo(
                        client,
                        message.chat.id,
                        file_path,
                        caption="📸 Instagram фото скачано через @azams_bot"
                    )

            except Exception as e:
                logger.error(f"❌ Instagram ошибка: {e}")
                
                # Предлагаем использовать YouTube вместо Instagram
                raise Exception(
                    "❌ Instagram временно недоступен\n\n"
                    "📸 **Проблемы с Instagram:**\n"
                    "• Instagram блокирует скачивание\n"
                    "• Требует постоянное обновление cookies\n"
                    "• Частые ограничения доступа\n\n"
                    "🎥 **Рекомендуем:**\n"
                    "• Использовать YouTube ссылки\n"
                    "• YouTube работает стабильно и быстро\n"
                    "• Поддерживает видео любого качества\n\n"
                    "💡 Отправьте ссылку на YouTube видео!"
                )
                
            finally:
                # Очистка
                if file_path and os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except:
                        pass
                if os.path.exists(tmp_dir):
                    try:
                        for file in os.listdir(tmp_dir):
                            os.remove(os.path.join(tmp_dir, file))
                        os.rmdir(tmp_dir)
                    except:
                        pass

        # Успешное завершение
        await message.delete()

    except Exception as e:
        logger.error(f"❌ Ошибка обработки для пользователя {user_id}: {e}")
        
        if status:
            try:
                error_msg = await message.reply_text(str(e))
                await asyncio.sleep(15)  # Дольше показываем сообщение об ошибке
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

# ------------------------- ЗАПУСК -------------------------
if __name__ == "__main__":
    # Очистка старых сессий
    old_sessions = ["fast_bot.session", "fast_bot.session-journal"]
    for session_file in old_sessions:
        if os.path.exists(session_file):
            try:
                os.remove(session_file)
                logger.info(f"🗑️ Удален старый файл сессии: {session_file}")
            except Exception as e:
                logger.warning(f"Не удалось удалить {session_file}: {e}")
    
    # Проверка cookies
    has_cookies = check_cookies_file()
    if has_cookies:
        logger.info("✅ Файл cookies.txt найден")
    else:
        logger.warning("⚠️ Файл cookies.txt не найден - Instagram недоступен")
    
    logger.info("🚀 Запуск бота с акцентом на YouTube...")
    logger.info("💡 Instagram работает ограниченно из-за блокировок платформы")
    app.run()
