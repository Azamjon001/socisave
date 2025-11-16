import requests
from telegram import Update
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext

# -----------------------------
# 1) SaveIG Downloader
# -----------------------------
def download_saveig(url):
    try:
        api = "https://saveig.app/api/ajaxSearch"
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": "Mozilla/5.0"
        }
        data = {
            "q": url,
            "t": "media",
            "lang": "en"
        }
        r = requests.post(api, headers=headers, data=data, timeout=10)
        js = r.json()

        if "medias" not in js:
            return None

        return [m["url"] for m in js["medias"]]

    except:
        return None


# -----------------------------
# 2) SnapInsta Downloader
# -----------------------------
def download_snapinsta(url):
    try:
        api = "https://snapinsta.app/api/ajaxSearch"
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": "Mozilla/5.0"
        }
        data = {
            "q": url,
            "t": "media",
            "lang": "en"
        }
        r = requests.post(api, headers=headers, data=data, timeout=10)
        js = r.json()

        if "medias" not in js:
            return None

        return [m["url"] for m in js["medias"]]

    except:
        return None


# -----------------------------
# 3) Toolzu Downloader
# -----------------------------
def download_toolzu(url):
    try:
        api = "https://toolzu.com/api/instagram/get-post"
        r = requests.get(api, params={"url": url}, timeout=10)
        js = r.json()

        if "data" not in js:
            return None

        return [item["download_url"] for item in js["data"]]

    except:
        return None


# ------------------------------------------
# UNIVERSAL DOWNLOADER – выбирает лучший API
# ------------------------------------------
def universal_instagram_downloader(insta_url):

    # 1) SaveIG
    result = download_saveig(insta_url)
    if result:
        return result

    # 2) SnapInsta
    result = download_snapinsta(insta_url)
    if result:
        return result

    # 3) Toolzu
    result = download_toolzu(insta_url)
    if result:
        return result

    return None


# -----------------------------
# Telegram handler
# -----------------------------
def handle_instagram(update: Update, context: CallbackContext):
    url = update.message.text.strip()

    update.message.reply_text("⏳ Загружаю...")

    files = universal_instagram_downloader(url)

    if not files:
        update.message.reply_text("❌ Не удалось скачать. Попробуйте другую ссылку.")
        return

    for link in files:
        if link.endswith(".mp4"):
            update.message.reply_video(video=link)
        else:
            update.message.reply_photo(photo=link)


def main():
    updater = Updater("6788128988:AAEMmCSafiiEqtS5UWQQxfo--W0On7B6Q08", use_context=True)
    dp = updater.dispatcher

    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_instagram))

    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
