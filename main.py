import os
import time
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from PIL import Image

app = FastAPI()

CACHE_DIR = "image_cache"
ORIGINALS_DIR = "hotel_images"

# --- КОНФИГУРАЦИЯ ИНВАЛИДАЦИИ КЭША ---
CACHE_TTL_SECONDS = 86400  # Время жизни кэша: 24 часа (86400 секунд)

os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(ORIGINALS_DIR, exist_ok=True)


# 1. Основной эндпоинт для отдачи и ресайза изображений (GET)
@app.get("/image")
def get_image(w: int, h: int, fmt: str, src: str):
    if fmt.lower() != "webp":
        raise HTTPException(status_code=400, detail="Поддерживается только формат webp")

    original_path = os.path.join(ORIGINALS_DIR, src)
    if not os.path.exists(original_path):
        raise HTTPException(status_code=404, detail="Оригинальное изображение не найдено")

    cache_filename = f"{src}_{w}x{h}.{fmt}"
    cache_path = os.path.join(CACHE_DIR, cache_filename)

    # ЛОГИКА АВТО-ИНВАЛИДАЦИИ ПО ВРЕМЕНИ (TTL)
    if os.path.exists(cache_path):
        file_age = time.time() - os.path.getmtime(cache_path)
        if file_age > CACHE_TTL_SECONDS:
            # Кэш устарел — удаляем старый файл, чтобы сгенерировать новый
            os.remove(cache_path)
        else:
            # Кэш актуален (ГОРЯЧИЙ ЗАПРОС)
            return FileResponse(cache_path, media_type="image/webp", headers={"X-Cache": "HIT"})

    # ОБРАБОТКА «НА ЛЕТУ» (ХОЛОДНЫЙ ЗАПРОС)
    try:
        with Image.open(original_path) as img:
            img_resized = img.resize((w, h), Image.Resampling.LANCZOS)
            img_resized.save(cache_path, format="WEBP", quality=80)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка обработки: {str(e)}")

    return FileResponse(cache_path, media_type="image/webp", headers={"X-Cache": "MISS"})


# 2. НОВЫЙ ЭНДПОИНТ ДЛЯ ПРИНУДИТЕЛЬНОЙ ИНВАЛИДАЦИИ КЭША (DELETE)
@app.delete("/image")
def invalidate_cache(src: str):
    """
    Удаляет все кэшированные размеры для указанного оригинального файла.
    Пример запроса: DELETE /image?src=test.jpg
    """
    if not src:
        raise HTTPException(status_code=400, detail="Параметр src не может быть пустым")

    deleted_count = 0

    # Сканируем папку кэша и удаляем все файлы, которые начинаются с имени оригинала
    # Например, удалит: test.jpg_300x200.webp, test.jpg_600x400.webp и т.д.
    for filename in os.listdir(CACHE_DIR):
        if filename.startswith(f"{src}_"):
            file_path = os.path.join(CACHE_DIR, filename)
            try:
                os.remove(file_path)
                deleted_count += 1
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Не удалось удалить файл {filename}: {str(e)}")

    if deleted_count == 0:
        return {"status": "success", "message": f"Кэш для файла {src} уже пуст или не существовал"}

    return {"status": "success", "message": f"Инвалидация выполнена успешно. Удалено файлов из кэша: {deleted_count}"}
