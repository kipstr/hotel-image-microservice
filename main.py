import os
import time
from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.responses import FileResponse
from PIL import Image

app = FastAPI()

CACHE_DIR = "image_cache"
ORIGINALS_DIR = "hotel_images"

CACHE_TTL_SECONDS = 86400  # 24 часа
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(ORIGINALS_DIR, exist_ok=True)


# --- РЕАЛИЗАЦИЯ POST ДЛЯ ЗАГРУЗКИ ФАЙЛОВ ---
@app.post("/upload")
async def upload_image(file: UploadFile = File(...)):
    """
    Загрузка оригинального изображения на сервер.
    """
    _, ext = os.path.splitext(file.filename.lower())
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Недопустимый формат. Разрешены: {ALLOWED_EXTENSIONS}")

    # Безопасное сохранение только имени файла (защита от Path Traversal)
    safe_name = os.path.basename(file.filename)
    target_path = os.path.join(ORIGINALS_DIR, safe_name)

    try:
        content = await file.read()
        with open(target_path, "wb") as f:
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка сохранения файла: {str(e)}")

    return {"status": "success", "filename": safe_name, "message": "Файл успешно загружен в hotel_images"}


# --- ОСНОВНОЙ ЭНДПОИНТ GET ---
@app.get("/image")
def get_image(
        w: int,
        h: int,
        src: str,
        fmt: str = Query("webp", description="Целевой формат: webp, jpeg, png"),
        quality: int = Query(80, ge=1, le=100, description="Качество сжатия от 1 до 100")
):
    # Защита от Path Traversal. Извлекаем только чистое имя файла!
    safe_src = os.path.basename(src)

    # Валидация целевого формата (теперь поддерживаем webp, jpeg, png)
    fmt = fmt.lower()
    if fmt == "jpg":
        fmt = "jpeg"
    if fmt not in ["webp", "jpeg", "png"]:
        raise HTTPException(status_code=400, detail="Поддерживаемые форматы fmt: webp, jpeg, png")

    _, ext = os.path.splitext(safe_src.lower())
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Недопустимое расширение оригинала: {ext}")

    original_path = os.path.join(ORIGINALS_DIR, safe_src)
    if not os.path.exists(original_path):
        raise HTTPException(status_code=404, detail="Оригинальное изображение не найдено")

    # Валидация структуры картинки
    try:
        with Image.open(original_path) as verify_img:
            verify_img.verify()
    except Exception:
        raise HTTPException(status_code=400, detail=f"Файл {safe_src} поврежден или не является картинкой")

    # Включаем динамический параметр quality в имя кэша
    original_size = os.path.getsize(original_path)
    cache_filename = f"{safe_src}_{w}x{h}_q{quality}.{fmt}"
    cache_path = os.path.join(CACHE_DIR, cache_filename)

    no_browser_cache_headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0"
    }

    # Проверка актуальности кэша
    if os.path.exists(cache_path):
        cache_mtime = os.path.getmtime(cache_path)
        original_mtime = os.path.getmtime(original_path)
        file_age = time.time() - cache_mtime

        if file_age > CACHE_TTL_SECONDS or original_mtime > cache_mtime:
            try:
                os.remove(cache_path)
            except OSError:
                pass
        else:
            return FileResponse(cache_path, media_type=f"image/{fmt}",
                                headers={"X-Cache": "HIT", **no_browser_cache_headers})

            # Обработка «на лету»
    try:
        with Image.open(original_path) as img:
            img_resized = img.resize((w, h), Image.Resampling.LANCZOS)

            # Конвертация в зависимости от fmt (с RGBA-адаптацией для JPEG)
            if fmt == "jpeg" and img_resized.mode in ("RGBA", "P"):
                img_resized = img_resized.convert("RGB")

            # Передаем динамический quality при сохранении
            img_resized.save(cache_path, format=fmt.upper(), quality=quality)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка обработки: {str(e)}")

    return FileResponse(cache_path, media_type=f"image/{fmt}", headers={"X-Cache": "MISS", **no_browser_cache_headers})


# Эндпоинт для принудительной инвалидации кэша (DELETE)
@app.delete("/image")
def invalidate_cache(src: str):
    safe_src = os.path.basename(src)
    deleted_count = 0
    for filename in os.listdir(CACHE_DIR):
        if filename.startswith(f"{safe_src}_"):
            file_path = os.path.join(CACHE_DIR, filename)
            try:
                os.remove(file_path)
                deleted_count += 1
            except Exception:
                pass
    return {"status": "success", "deleted_count": deleted_count}
