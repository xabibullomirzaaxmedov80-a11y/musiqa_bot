import asyncio
import logging
import os
import tempfile
from typing import Any, List

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

import yt_dlp

# Load environment variables from .env file
load_dotenv()

# Get token from environment
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is missing in .env file")

# Initialize bot and dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

async def search_youtube(query: str) -> List[dict]:
    """
    Search YouTube and return a list of top 5 results.
    """
    ydl_opts = {
        'extract_flat': True,
        'quiet': True,
        'default_search': 'ytsearch5',
    }
    def _search():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch5:{query}", download=False)
            if 'entries' in info:
                return info['entries']
            return []
    return await asyncio.to_thread(_search)

async def download_audio(video_id: str) -> dict[str, Any]:
    """
    Download the audio for a specific video ID.
    """
    temp_dir = tempfile.mkdtemp()
    
    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
        'noplaylist': True,
        'quiet': True,
    }
    
    def _download():
        url = f"https://www.youtube.com/watch?v={video_id}"
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            files = os.listdir(temp_dir)
            if len(files) > 0:
                downloaded_file = files[0]
                return {
                    'filepath': os.path.join(temp_dir, downloaded_file),
                    'title': info.get('title', 'Unknown Title'),
                }
            return None
            
    return await asyncio.to_thread(_download)


@dp.message(CommandStart())
async def command_start_handler(message: types.Message) -> None:
    await message.answer(f"Salom, {message.from_user.full_name}! 🎧\nMusiqa izlash uchun qo'shiq nomini yozing, men sizga variantlar taqdim etaman.")

@dp.message(Command("help"))
async def command_help_handler(message: types.Message) -> None:
    await message.answer("Shunchaki musiqa nomini yozing.\nMasalan: `Yulduz Usmonova - Xasta bo'lma`")

@dp.message(F.text)
async def process_music_search(message: types.Message) -> None:
    query = message.text
    status_msg = await message.answer(f"🔍 '{query}' bo'yicha qidirilmoqda...")
    
    try:
        results = await search_youtube(query)
        if not results:
            await status_msg.edit_text("❌ Kechirasiz, hech narsa topilmadi.")
            return

        builder = InlineKeyboardBuilder()
        for idx, entry in enumerate(results):
            title = entry.get('title', 'Noma\'lum')
            video_id = entry.get('id')
            channel = entry.get('uploader', '')
            
            button_text = f"{idx + 1}. {title}"
            if channel:
                button_text += f" ({channel})"
            
            # Callback data length must be <= 64 bytes
            builder.row(InlineKeyboardButton(
                text=button_text[:60], # Limit text length to avoid too long buttons
                callback_data=f"dl_{video_id}"
            ))
        
        await status_msg.edit_text("🎵 Quyidagi variantlardan birini tanlang:", reply_markup=builder.as_markup())

    except Exception as e:
        logging.error(f"Search error: {e}")
        await status_msg.edit_text("⚠️ Qidiruvda xatolik yuz berdi.")

@dp.callback_query(F.data.startswith("dl_"))
async def process_download_callback(callback: types.CallbackQuery):
    video_id = callback.data[3:]
    await callback.message.edit_text("⏳ Musiqa yuklab olinmoqda... Iltimos kuting.")
    
    try:
        result = await download_audio(video_id)
        if result and 'filepath' in result:
            filepath = result['filepath']
            title = result['title']
            
            audio = FSInputFile(filepath)
            await bot.send_audio(
                chat_id=callback.message.chat.id,
                audio=audio,
                title=title,
                caption="🎵 Musiqa Bot orqali yuklandi!"
            )
            
            try:
                os.remove(filepath)
            except Exception as e:
                logging.error(f"Failed to delete {filepath}: {e}")
                
            await callback.message.delete()
        else:
            await callback.message.edit_text("❌ Musiqani yuklashda xatolik yuz berdi.")
    except Exception as e:
        logging.error(f"Download error: {e}")
        await callback.message.edit_text("⚠️ Yuklab olishda xatolik yuz berdi.")
    
    await callback.answer()

async def main() -> None:
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
