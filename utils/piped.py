"""
Piped API client - Free YouTube proxy for bypassing datacenter IP blocks.
Uses multiple public Piped instances with automatic fallback.
"""

import aiohttp
import random
import re
import urllib.parse
from typing import Optional, List, Dict

PIPED_INSTANCES = [
    "https://pipedapi.kavin.rocks",
    "https://pipedapi.adminforge.de",
    "https://pipedapi.r4fo.com",
    "https://pipedapi.leptons.xyz",
    "https://pipedapi.moomoo.me",
    "https://pipedapi.drgns.space",
]


class PipedClient:
    """Client for the Piped API with automatic instance fallback."""

    def __init__(self):
        self.instances = PIPED_INSTANCES.copy()
        self._last_working = None

    def _get_ordered_instances(self) -> list:
        instances = self.instances.copy()
        random.shuffle(instances)
        if self._last_working and self._last_working in instances:
            instances.remove(self._last_working)
            instances.insert(0, self._last_working)
        return instances

    async def _request(self, path: str) -> Optional[dict]:
        for instance in self._get_ordered_instances():
            try:
                url = f"{instance}{path}"
                timeout = aiohttp.ClientTimeout(total=10)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            self._last_working = instance
                            return await resp.json()
            except Exception as e:
                print(f"[PIPED] Instance {instance} failed: {e}")
                continue
        print("[PIPED] All instances failed!")
        return None

    @staticmethod
    def extract_video_id(url: str) -> Optional[str]:
        pattern = r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|music\.youtube\.com/watch\?v=)([a-zA-Z0-9_-]{11})'
        match = re.search(pattern, url)
        return match.group(1) if match else None

    async def search(self, query: str, limit: int = 5) -> List[Dict]:
        encoded = urllib.parse.quote(query)
        for filter_type in ["music_songs", "videos"]:
            data = await self._request(f"/search?q={encoded}&filter={filter_type}")
            if data and "items" in data and len(data["items"]) > 0:
                results = []
                for item in data["items"][:limit]:
                    if item.get("type") != "stream":
                        continue
                    video_url = item.get("url", "")
                    video_id = video_url.replace("/watch?v=", "") if video_url else ""
                    results.append({
                        "title": item.get("title", "Unknown"),
                        "url": f"https://www.youtube.com/watch?v={video_id}",
                        "duration": item.get("duration", 0) or 0,
                        "thumbnail": item.get("thumbnail", ""),
                    })
                if results:
                    print(f"[PIPED] Search found {len(results)} results")
                    return results
        return []

    async def get_stream(self, video_id: str) -> Optional[Dict]:
        data = await self._request(f"/streams/{video_id}")
        if not data:
            return None
        audio_streams = data.get("audioStreams", [])
        if not audio_streams:
            print(f"[PIPED] No audio streams for {video_id}")
            return None
        audio_streams.sort(key=lambda x: x.get("bitrate", 0), reverse=True)
        best = None
        for stream in audio_streams:
            mime = stream.get("mimeType", "")
            codec = stream.get("codec", "")
            if "audio" in mime:
                if best is None:
                    best = stream
                if "opus" in codec or "opus" in mime:
                    best = stream
                    break
        if not best:
            best = audio_streams[0]
        result = {
            "stream_url": best.get("url", ""),
            "title": data.get("title", "Unknown"),
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "duration": data.get("duration", 0) or 0,
            "thumbnail": data.get("thumbnailUrl", ""),
        }
        quality = best.get("quality", "?")
        print(f"[PIPED] Got stream for '{result['title']}' ({quality})")
        return result

    async def get_stream_from_url(self, youtube_url: str) -> Optional[Dict]:
        video_id = self.extract_video_id(youtube_url)
        if not video_id:
            return None
        return await self.get_stream(video_id)


piped = PipedClient()
