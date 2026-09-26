import aiohttp
import re
from typing import Optional


async def fetch_lyrics(title: str, artist: str = "", genius_token: str = "") -> Optional[str]:
    """
    Fetch lyrics for a song.
    Uses a free lyrics API first, falls back to Genius if token provided.
    """
    # Clean up title - remove common YouTube suffixes
    clean_title = re.sub(
        r'\s*[\(\[](official|music|lyric|audio|video|mv|hd|hq|4k|visualizer|feat\.?|ft\.?).*?[\)\]]',
        '', title, flags=re.IGNORECASE
    ).strip()

    # Try lyrics.ovh (free, no API key needed)
    lyrics = await _fetch_from_lyrics_ovh(clean_title, artist)
    if lyrics:
        return lyrics

    # Try lrclib (free, no API key needed)
    lyrics = await _fetch_from_lrclib(clean_title, artist)
    if lyrics:
        return lyrics

    return None


async def _fetch_from_lyrics_ovh(title: str, artist: str) -> Optional[str]:
    """Fetch from lyrics.ovh free API."""
    try:
        # If we have both artist and title
        if artist:
            url = f"https://api.lyrics.ovh/v1/{artist}/{title}"
        else:
            # Try to split "Artist - Title" format
            parts = title.split(" - ", 1)
            if len(parts) == 2:
                url = f"https://api.lyrics.ovh/v1/{parts[0].strip()}/{parts[1].strip()}"
            else:
                return None

        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    lyrics = data.get("lyrics", "")
                    if lyrics and len(lyrics.strip()) > 20:
                        return _truncate_lyrics(lyrics.strip())
    except Exception:
        pass
    return None


async def _fetch_from_lrclib(title: str, artist: str) -> Optional[str]:
    """Fetch from lrclib.net free API."""
    try:
        params = {"track_name": title}
        if artist:
            params["artist_name"] = artist
        else:
            parts = title.split(" - ", 1)
            if len(parts) == 2:
                params["artist_name"] = parts[0].strip()
                params["track_name"] = parts[1].strip()

        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://lrclib.net/api/search",
                params=params,
                timeout=aiohttp.ClientTimeout(total=10),
                headers={"User-Agent": "DiscordMusicBot/1.0"}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data and len(data) > 0:
                        # Prefer synced lyrics, fall back to plain
                        entry = data[0]
                        lyrics = entry.get("plainLyrics") or entry.get("syncedLyrics", "")
                        if lyrics and len(lyrics.strip()) > 20:
                            # Remove timestamp tags from synced lyrics
                            clean = re.sub(r'\[\d{2}:\d{2}\.\d{2,3}\]\s*', '', lyrics)
                            return _truncate_lyrics(clean.strip())
    except Exception:
        pass
    return None


def _truncate_lyrics(lyrics: str, max_length: int = 3900) -> str:
    """Truncate lyrics to fit in Discord embed (max 4096 chars)."""
    if len(lyrics) <= max_length:
        return lyrics
    # Find a good break point
    truncated = lyrics[:max_length]
    last_newline = truncated.rfind('\n')
    if last_newline > max_length * 0.8:
        truncated = truncated[:last_newline]
    return truncated + "\n\n... (lyrics truncated)"
