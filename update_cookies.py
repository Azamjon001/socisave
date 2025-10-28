import os
import shutil
import time

# Путь к новому cookies-файлу (например, загружен через браузер)
NEW_COOKIES = "/mnt/data/new_cookies.txt"
TARGET_COOKIES = "/app/cookies.txt"

def update_cookies():
    if os.path.exists(NEW_COOKIES):
        shutil.copy(NEW_COOKIES, TARGET_COOKIES)
        print("✅ Cookies обновлены.")
    else:
        print("⚠️ Новый cookies.txt не найден.")

if __name__ == "__main__":
    while True:
        update_cookies()
        time.sleep(12 * 3600)  # каждые 12 часов

