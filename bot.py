import os
import asyncio
import logging
import tempfile
import yt_dlp
import re
import time
import random
import requests
import json
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

# ------------------------- INSTAGRAM ФУНКЦИИ (ОБНОВЛЕННЫЕ) -------------------------

def check_cookies_file():
    """Проверяем cookies файл"""
    if not os.path.exists("cookies.txt"):
        logger.error("❌ Файл cookies.txt не найден!")
        return False
    
    # Проверяем что файл не пустой
    file_size = os.path.getsize("cookies.txt")
    if file_size == 0:
        logger.error("❌ Файл cookies.txt пустой!")
        return False
        
    logger.info("✅ Файл cookies.txt найден")
    return True

def download_instagram_with_retry(url: str, out_path: str):
    """Скачивание Instagram с несколькими попытками и разными методами"""
    if not check_cookies_file():
        raise FileNotFoundError("Файл cookies.txt не найден или пустой")
    
    methods = [
        {
            "name": "Простой метод",
            "opts": {
                "outtmpl": os.path.join(out_path, "ig_%(title)s.%(ext)s"),
                "cookiefile": "cookies.txt",
                "quiet": False,
                "ignoreerrors": True,
                "retries": 2,
            }
        },
        {
            "name": "Метод с форматом", 
            "opts": {
                "outtmpl": os.path.join(out_path, "ig_media.%(ext)s"),
                "cookiefile": "cookies.txt",
                "quiet": False,
                "ignoreerrors": True,
                "retries": 3,
                "format": "best"
            }
        },
        {
            "name": "Агрессивный метод",
            "opts": {
                "outtmpl": os.path.join(out_path, "instagram.%(ext)s"),
                "cookiefile": "cookies.txt", 
                "quiet": False,
                "ignoreerrors": True,
                "retries": 5,
                "fragment_retries": 5,
                "skip_unavailable_fragments": True,
                "extract_flat": False,
            }
        }
    ]
    
    last_error = None
    
    for method in methods:
        try:
            logger.info(f"🔄 Пробую {method['name']}...")
            
            with yt_dlp.YoutubeDL(method['opts']) as ydl:
                info = ydl.extract_info(url, download=True)
                
                # Ищем скачанный файл
                for file in os.listdir(out_path):
                    file_path = os.path.join(out_path, file)
                    if os.path.isfile(file_path) and os.path.getsize(file_path) > 0:
                        logger.info(f"✅ Найден файл: {file_path}")
                        return file_path, info
                
                raise Exception("Файл не найден после скачивания")
                
        except Exception as e:
            last_error = e
            logger.warning(f"❌ {method['name']} не сработал: {e}")
            time.sleep(2)  # Задержка между попытками
            continue
    
    raise Exception(f"Все методы не сработали. Последняя ошибка: {last_error}")

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

# ------------------------- INSTAGRAM ALTERNATIVE METHODS -------------------------

def test_instagram_access():
    """Тестируем доступ к Instagram"""
    if not check_cookies_file():
        return False, "Cookies файл не найден"
    
    test_url = "https://www.instagram.com/p/CuZkKzOsErk/"  # Публичный пост для теста
    
    try:
        ydl_opts = {
            "quiet": True,
            "skip_download": True,
            "cookiefile": "cookies.txt",
            "ignoreerrors": True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(test_url, download=False)
            if info:
                return True, "Instagram доступен"
            else:
                return False, "Не удалось получить информацию о тестовом посте"
                
    except Exception as e:
        return False, f"Ошибка доступа к Instagram: {e}"

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
    
    # Тестируем Instagram доступ
    ig_status, ig_message = test_instagram_access()
    ig_status_text = "✅ Instagram доступен" if ig_status else f"❌ {ig_message}"
    
    await message.reply_text(
        f"Привет! 👋\n\n"
        f"📥 Отправь ссылку на:\n"
        f"• YouTube (видео, Shorts) - ✅ Работает\n"
        f"• Instagram - {ig_status_text}\n\n"
        f"⚡ Быстрое скачивание!\n"
        f"🔄 Бот перезапускается каждые 12 часов"
    )

@app.on_message(filters.command(["help", "info"]))
async def help_command(client, message):
    message_id = f"help_{message.id}_{message.from_user.id}"
    
    if message_id in processed_messages:
        return
        
    processed_messages.add(message_id)
    
    # Тестируем Instagram доступ
    ig_status, ig_message = test_instagram_access()
    
    help_text = (
        "🤖 **Помощь по боту**\n\n"
        "📥 **YouTube:**\n"
        "• Видео любой длительности\n"
        "• YouTube Shorts\n"
        "• Быстрое скачивание ✅\n\n"
    )
    
    if ig_status:
        help_text += (
            "📸 **Instagram:**\n"
            "• Видео и рилсы\n" 
            "• Фото и посты\n"
            "• Требуется cookies.txt ✅\n\n"
        )
    else:
        help_text += (
            "📸 **Instagram:**\n"
            f"• Временно недоступен ❌\n"
            f"• Причина: {ig_message}\n\n"
        )
    
    help_text += "⚡ Просто отправь ссылку!"
    
    await message.reply_text(help_text)

@app.on_message(filters.command("status"))
async def status_command(client, message):
    """Проверка статуса бота"""
    ig_status, ig_message = test_instagram_access()
    
    status_text = (
        "🤖 **Статус бота**\n\n"
        f"📊 Обработано сообщений: {len(processed_messages)}\n"
        f"👤 Активных пользователей: {len(user_processing)}\n\n"
        f"🎥 **YouTube:** ✅ Работает\n"
        f"📸 **Instagram:** {'✅ Работает' if ig_status else '❌ Недоступен'}\n"
    )
    
    if not ig_status:
        status_text += f"\n🔧 Проблема Instagram: {ig_message}"
    
    await message.reply_text(status_text)

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
            "📥 Поддерживаются только:\n"
            "• YouTube (youtube.com, youtu.be)\n"
            "• Instagram (instagram.com)\n\n"
            "⚡ Отправьте правильную ссылку"
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
            # YouTube обработка
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
            # Instagram обработка
            tmp_dir = tempfile.mkdtemp()
            file_path = None
            
            try:
                # Сначала проверяем доступ
                ig_status, ig_message = test_instagram_access()
                if not ig_status:
                    raise Exception(f"Instagram недоступен: {ig_message}")
                
                await status.edit_text("📥 Скачиваю Instagram контент...")
                
                # Пробуем скачать с повторными попытками
                file_path, info = await asyncio.to_thread(download_instagram_with_retry, url, tmp_dir)
                
                if not file_path:
                    raise Exception("Не удалось скачать контент")
                
                # Определяем тип медиа
                media_type = get_media_type(file_path)
                await status.edit_text("📤 Отправляю...")
                
                if media_type == "video":
                    await safe_send_video(
                        client,
                        message.chat.id,
                        file_path,
                        caption="📥 Instagram видео скачано через @azams_bot"
                    )
                    logger.info("✅ Instagram видео отправлено")
                    
                elif media_type == "photo":
                    await safe_send_photo(
                        client,
                        message.chat.id,
                        file_path,
                        caption="📸 Instagram фото скачано через @azams_bot"
                    )
                    logger.info("✅ Instagram фото отправлено")
                    
                else:
                    # Пробуем отправить как видео
                    try:
                        await safe_send_video(
                            client,
                            message.chat.id,
                            file_path,
                            caption="📥 Instagram контент скачан через @azams_bot"
                        )
                    except:
                        # Если не видео, пробуем как фото
                        await safe_send_photo(
                            client,
                            message.chat.id,
                            file_path,
                            caption="📸 Instagram контент скачан через @azams_bot"
                        )

            except Exception as e:
                logger.error(f"❌ Instagram ошибка: {e}")
                
                # Более понятное сообщение об ошибке
                error_msg = str(e)
                if "cookies" in error_msg.lower():
                    user_msg = "❌ Проблема с cookies файлом\n\nУбедитесь что:\n• Файл cookies.txt существует\n• Он не пустой\n• Cookies актуальные"
                elif "login" in error_msg.lower() or "auth" in error_msg.lower():
                    user_msg = "❌ Требуется авторизация\n\nInstagram требует вход в аккаунт. Проверьте cookies файл."
                elif "private" in error_msg.lower():
                    user_msg = "❌ Приватный аккаунт\n\nЭтот Instagram аккаунт приватный. Нужно быть подписчиком."
                elif "unavailable" in error_msg.lower():
                    user_msg = "❌ Контент недоступен\n\nЭтот пост может быть удален или скрыт."
                else:
                    user_msg = f"❌ Не удалось скачать Instagram контент\n\nПопробуйте:\n• Другую ссылку\n• Проверить доступность поста\n• Обновить cookies файл"
                
                raise Exception(user_msg)
                
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
                await asyncio.sleep(10)
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
    
    # Проверка cookies и тест Instagram
    ig_status, ig_message = test_instagram_access()
    if ig_status:
        logger.info("✅ Instagram доступен")
    else:
        logger.warning(f"⚠️ Instagram недоступен: {ig_message}")
    
    logger.info("🚀 Запуск бота с улучшенной обработкой ошибок...")
    app.run()
