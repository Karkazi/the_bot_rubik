"""
Обработчик команды /showracemenu для MAX через библиотеку maxapi.
Использует InputMedia(path=...) для отправки файла по локальному пути.
"""
import random
from pathlib import Path

# Папка с картинками относительно корня проекта (adapters/max/ -> корень на 2 уровня вверх)
PICTURES_DIR = Path(__file__).resolve().parents[2] / "Pict"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp"}


def get_random_image(directory: Path) -> Path | None:
    """Возвращает случайный файл-изображение из папки или None."""
    if not directory.is_dir():
        return None
    images = [
        f for f in directory.iterdir()
        if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
    ]
    if not images:
        return None
    return random.choice(images)


def register_showracemenu(dp):
    """
    Регистрирует обработчик /showracemenu на диспетчере maxapi.
    dp — экземпляр maxapi.Dispatcher.
    """
    from maxapi.types import InputMedia, Command, MessageCreated

    @dp.message_created(Command("showracemenu"))
    async def show_race_menu(event: MessageCreated):
        image_path = get_random_image(PICTURES_DIR)
        if image_path is None:
            await event.message.answer("😔 В папке нет картинок!")
            return
        await event.message.answer(
            text="🎲 Вот твоя случайная картинка!",
            attachments=[InputMedia(path=str(image_path))],
        )
