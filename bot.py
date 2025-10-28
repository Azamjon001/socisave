import os
import asyncio
import logging
import tempfile
import yt_dlp
import re
import time
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

# Все остальные функции остаются без изменений...
# [здесь все ваши функции extract_first_url, normalize_url, и т.д.]

@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text(
        "Привет! 👋\n\n"
        "📥 Отправь ссылку на Instagram или YouTube — я скачаю видео для тебя.\n\n"
        "⚡ Бот автоматически перезапускается каждые 12 часов для стабильной работы!"
    )

# [остальные обработчики без изменений]

if __name__ == "__main__":
    # Очистка старых сессий
    old_sessions = ["fast_bot.session", "fast_bot.session-journal"]
    for session_file in old_sessions:
        if os.path.exists(session_file):
            try:
                os.remove(session_file)
            except:
                pass
    
    logger.info("🚀 Запуск бота...")
    logger.info("🔄 Автоперезапуск каждые 12 часов через Railway")
    app.run()
