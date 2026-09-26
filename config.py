import os
from dotenv import load_dotenv

load_dotenv()

# Discord
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
GENIUS_API_TOKEN = os.getenv("GENIUS_API_TOKEN", "")

# Bot settings
BOT_PREFIX = "!"
BOT_COLOR = 0x2ECC71  # Embed color (green)
BOT_ERROR_COLOR = 0xE74C3C  # Error embed color (red)
BOT_WARN_COLOR = 0xF39C12  # Warning embed color (yellow)

# Music settings
DEFAULT_VOLUME = 50  # 0-100
MAX_QUEUE_SIZE = 500
INACTIVITY_TIMEOUT = 300  # 5 minutes - auto disconnect

# YT-DLP options
COOKIES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt")

YTDL_FORMAT_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch5",
    "source_address": "0.0.0.0",
    "extract_flat": False,
    "force_generic_extractor": False,
    "geo_bypass": True,
    "js_runtimes": {"ejs": {}, "deno": {}, "nodejs": {}},
    "nocheckcertificate": True,
    "extractor_args": {
        "youtube": {
            "player_client": ["ios", "android"],
        }
    },
}

import base64

# Automatically write cookies.txt from environment variable if provided
if os.getenv("YOUTUBE_COOKIES_BASE64"):
    try:
        decoded_cookies = base64.b64decode(os.getenv("YOUTUBE_COOKIES_BASE64")).decode('utf-8')
        with open(COOKIES_FILE, 'w', encoding='utf-8') as cf:
            cf.write(decoded_cookies)
        print("Loaded cookies from YOUTUBE_COOKIES_BASE64 variable")
    except Exception as e:
        print(f"Failed to decode cookies: {e}")

if os.path.exists(COOKIES_FILE):
    YTDL_FORMAT_OPTIONS["cookiefile"] = COOKIES_FILE

FFMPEG_PATH = r"C:\Users\Admin\AppData\Local\Microsoft\WinGet\Links\ffmpeg.exe"

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 10 -analyzeduration 0 -probesize 32768 -nostdin",
    "options": "-vn -bufsize 64k",
}