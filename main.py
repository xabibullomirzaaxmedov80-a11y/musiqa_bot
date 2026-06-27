import asyncio
import logging
import os
import tempfile
import re
from typing import Any, List

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.types import (
    FSInputFile, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent
)
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

async def download_audio(video_id: str, progress_hook=None) -> dict[str, Any]:
    """
    Download the audio for a specific video ID.
    """
    temp_dir = tempfile.mkdtemp()
    
    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
        'noplaylist': True,
        'quiet': True,
        'nocolor': True,
        'extractor_args': {'youtube': {'player_client': ['default', 'web_embedded', 'ios', 'tv']}}
    }
    
    if progress_hook:
        ydl_opts['progress_hooks'] = [progress_hook]

    
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
async def command_start_handler(message: types.Message, command: CommandObject = None) -> None:
    if command and command.args and command.args.startswith("dl_"):
        video_id = command.args[3:]
        status_msg = await message.answer("⏳ Musiqa yuklash boshlanmoqda... 0%")
        await execute_download(message.chat.id, status_msg, video_id)
        return

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
    await callback.message.edit_text("⏳ Musiqa yuklash boshlanmoqda... 0%")
    await execute_download(callback.message.chat.id, callback.message, video_id)
    try:
        await callback.answer()
    except Exception:
        pass

async def execute_download(chat_id: int, status_message: types.Message, video_id: str):
    progress_state = {'percent': '0%', 'status': 'starting'}
    def hook(d):
        if d['status'] == 'downloading':
            percent = d.get('_percent_str', '0%').strip()
            # Clean ANSI colors if any are left
            clean_percent = re.sub(r'\x1b\[[0-9;]*m', '', percent)
            progress_state['percent'] = clean_percent
            progress_state['status'] = 'downloading'
        elif d['status'] == 'finished':
            progress_state['status'] = 'finished'

    download_task = asyncio.create_task(download_audio(video_id, hook))
    
    last_percent = ""
    while not download_task.done():
        await asyncio.sleep(2)
        if progress_state['status'] == 'downloading' and progress_state['percent'] != last_percent:
            try:
                await status_message.edit_text(f"⏳ Musiqa yuklab olinmoqda... {progress_state['percent']}")
                last_percent = progress_state['percent']
            except Exception:
                pass
                
    try:
        result = await download_task
        if result and 'filepath' in result:
            filepath = result['filepath']
            title = result['title']
            
            audio = FSInputFile(filepath)
            await status_message.edit_text("⏳ Fayl Telegramga jo'natilmoqda...")
            await bot.send_audio(
                chat_id=chat_id,
                audio=audio,
                title=title,
                caption="🎵 Musiqa Bot orqali yuklandi!"
            )
            
            try:
                os.remove(filepath)
            except Exception as e:
                logging.error(f"Failed to delete {filepath}: {e}")
                
            await status_message.delete()
        else:
            await status_message.edit_text("❌ Musiqani yuklashda xatolik yuz berdi.")
    except Exception as e:
        logging.error(f"Download error: {e}")
        await status_message.edit_text("⚠️ Yuklab olishda xatolik yuz berdi.")

@dp.inline_query()
async def inline_query_handler(inline_query: InlineQuery, bot: Bot):
    query = inline_query.query.strip()
    if not query:
        return
        
    results_list = await search_youtube(query)
    bot_info = await bot.get_me()
    
    results = []
    for idx, entry in enumerate(results_list):
        video_id = entry.get('id')
        title = entry.get('title', 'Noma\'lum')
        channel = entry.get('uploader', '')
        
        dl_url = f"https://t.me/{bot_info.username}?start=dl_{video_id}"
        
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬇️ Yuklab olish", url=dl_url)]
        ])
        
        content = InputTextMessageContent(
            message_text=f"🎵 {title}\n👤 {channel}"
        )
        
        results.append(
            InlineQueryResultArticle(
                id=video_id,
                title=title,
                description=channel,
                input_message_content=content,
                reply_markup=markup,
                thumbnail_url=f"https://img.youtube.com/vi/{video_id}/default.jpg"
            )
        )
        
    await inline_query.answer(results, cache_time=60, is_personal=False)

async def main() -> None:
    # Render Free Tier uchun oddiy web server (Portni band qilish uchun)
    from aiohttp import web
    async def handle(request):
        return web.Response(text="Bot is running!")
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logging.info(f"Dummy web server started on port {port}")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
