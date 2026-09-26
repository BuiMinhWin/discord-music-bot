import asyncio
import functools
import math
import re
from datetime import datetime
from typing import Optional

import discord
import yt_dlp
from discord.ext import commands

from config import (
    BOT_COLOR, BOT_ERROR_COLOR, BOT_WARN_COLOR,
    DEFAULT_VOLUME, FFMPEG_OPTIONS, FFMPEG_PATH, YTDL_FORMAT_OPTIONS,
    INACTIVITY_TIMEOUT, GENIUS_API_TOKEN,
)
from utils.lyrics import fetch_lyrics
from utils.music_queue import LoopMode, MusicQueue, Song


# Suppress yt-dlp console noise
yt_dlp.utils.bug_reports_message = lambda *args, **kwargs: ""


class YTDLSource:
    """Handles YouTube audio extraction using yt-dlp."""

    ytdl = yt_dlp.YoutubeDL(YTDL_FORMAT_OPTIONS)

    @classmethod
    async def extract_info(cls, query: str, *, loop=None) -> list[dict]:
        """Extract song info from URL or search query."""
        loop = loop or asyncio.get_event_loop()

        # Determine if it's a URL or search query
        url_pattern = re.compile(r'https?://(?:www\.)?(?:youtube\.com|youtu\.be|music\.youtube\.com)')
        is_url = bool(url_pattern.match(query))

        if is_url:
            # Strip playlist/radio params so we only fetch the single video
            from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
            parsed = urlparse(query)
            params = parse_qs(parsed.query)
            if 'v' in params and ('list' in params or 'start_radio' in params):
                clean_params = urlencode({'v': params['v'][0]})
                query = urlunparse(parsed._replace(query=clean_params))
                print(f"[YTDL] Cleaned URL to: {query}")
        else:
            query = f"ytsearch5:{query}"

        try:
            data = await loop.run_in_executor(
                None,
                functools.partial(cls.ytdl.extract_info, query, download=False)
            )
        except Exception as e:
            raise Exception(f"Could not extract info: {str(e)}")

        if not data:
            return []

        entries = data.get("entries", [data])
        results = []

        for entry in entries:
            if entry is None:
                continue
            results.append({
                "title": entry.get("title", "Unknown"),
                "url": entry.get("webpage_url", entry.get("url", "")),
                "stream_url": entry.get("url", ""),
                "duration": entry.get("duration", 0) or 0,
                "thumbnail": entry.get("thumbnail", ""),
            })

        return results

    @classmethod
    async def get_stream_url(cls, url: str, *, loop=None) -> Optional[dict]:
        """Re-extract stream URL (they expire)."""
        loop = loop or asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(
                None,
                functools.partial(cls.ytdl.extract_info, url, download=False)
            )
            if data:
                return {
                    "stream_url": data.get("url", ""),
                    "title": data.get("title", "Unknown"),
                    "duration": data.get("duration", 0) or 0,
                    "thumbnail": data.get("thumbnail", ""),
                }
        except Exception:
            pass
        return None


class Music(commands.Cog):
    """Music commands for the bot."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.queues: dict[int, MusicQueue] = {}  # guild_id -> MusicQueue
        self.volumes: dict[int, float] = {}  # guild_id -> volume (0.0 - 1.0)
        self.inactivity_tasks: dict[int, asyncio.Task] = {}
        self.now_playing_messages: dict[int, discord.Message] = {}

    def get_queue(self, guild_id: int) -> MusicQueue:
        if guild_id not in self.queues:
            self.queues[guild_id] = MusicQueue()
        return self.queues[guild_id]

    def get_volume(self, guild_id: int) -> float:
        return self.volumes.get(guild_id, DEFAULT_VOLUME / 100)

    def _make_embed(self, title: str, description: str = "", color: int = BOT_COLOR) -> discord.Embed:
        embed = discord.Embed(title=title, description=description, color=color)
        embed.timestamp = datetime.utcnow()
        return embed

    # ──────────────────────────────────────────────
    #  Voice Connection Helpers
    # ──────────────────────────────────────────────

    async def _ensure_voice(self, ctx: discord.ApplicationContext, deferred: bool = False) -> Optional[discord.VoiceClient]:
        """Ensure bot is in the user's voice channel."""
        send = ctx.followup.send if deferred else ctx.respond
        if not ctx.author.voice:
            print(f"[VOICE] User {ctx.author} is not in a voice channel")
            embed = self._make_embed("❌ Error", "You need to be in a voice channel!", BOT_ERROR_COLOR)
            await send(embed=embed, ephemeral=True)
            return None

        channel = ctx.author.voice.channel

        if ctx.voice_client:
            if ctx.voice_client.channel.id != channel.id:
                print(f"[VOICE] Moving bot from {ctx.voice_client.channel.name} to {channel.name}")
                await ctx.voice_client.move_to(channel)
            return ctx.voice_client

        try:
            print(f"[VOICE] Connecting to voice channel '{channel.name}' (timeout=15s)...")
            vc = await channel.connect(timeout=15.0, reconnect=True)
            print(f"[VOICE] Connected successfully to '{channel.name}'!")
            return vc
        except Exception as e:
            import traceback as tb
            print(f"[VOICE] Connection error: {type(e).__name__}: {e}")
            tb.print_exc()
            embed = self._make_embed("❌ Error", f"Cannot connect to voice channel: {e}", BOT_ERROR_COLOR)
            await send(embed=embed, ephemeral=True)
            return None

    async def _inactivity_check(self, guild_id: int):
        """Disconnect after inactivity timeout."""
        await asyncio.sleep(INACTIVITY_TIMEOUT)
        guild = self.bot.get_guild(guild_id)
        if guild and guild.voice_client:
            if not guild.voice_client.is_playing():
                await guild.voice_client.disconnect()
                self.get_queue(guild_id).clear_all()
                # Try to send a message
                if guild_id in self.now_playing_messages:
                    try:
                        channel = self.now_playing_messages[guild_id].channel
                        embed = self._make_embed("👋 Disconnected", "Left due to inactivity.", BOT_WARN_COLOR)
                        await channel.send(embed=embed)
                    except Exception:
                        pass

    def _reset_inactivity(self, guild_id: int):
        """Reset the inactivity timer."""
        if guild_id in self.inactivity_tasks:
            self.inactivity_tasks[guild_id].cancel()
        self.inactivity_tasks[guild_id] = asyncio.create_task(self._inactivity_check(guild_id))

    # ──────────────────────────────────────────────
    #  Playback Engine
    # ──────────────────────────────────────────────

    async def _play_next(self, guild_id: int, text_channel: discord.TextChannel):
        """Play the next song in queue."""
        guild = self.bot.get_guild(guild_id)
        if not guild or not guild.voice_client:
            return

        queue = self.get_queue(guild_id)
        song = queue.next()

        if not song:
            self._reset_inactivity(guild_id)
            embed = self._make_embed("📭 Queue Empty", "No more songs in the queue. Add more with `/play`!")
            try:
                await text_channel.send(embed=embed)
            except Exception:
                pass
            return

        # Re-extract stream URL (they expire quickly)
        fresh = await YTDLSource.get_stream_url(song.url)
        if fresh:
            song.stream_url = fresh["stream_url"]

        volume = self.get_volume(guild_id)
        ffmpeg_opts = FFMPEG_OPTIONS.copy()
        ffmpeg_opts["options"] = f'-vn -bufsize 64k -filter:a "volume={volume}"'

        try:
            source = discord.FFmpegPCMAudio(song.stream_url, executable=FFMPEG_PATH, **ffmpeg_opts)

            def after_playing(error):
                if error:
                    print(f"Player error: {error}")
                asyncio.run_coroutine_threadsafe(
                    self._play_next(guild_id, text_channel),
                    self.bot.loop
                )

            guild.voice_client.play(source, after=after_playing)

            # Send now playing embed
            embed = self._make_now_playing_embed(song, queue)
            try:
                msg = await text_channel.send(embed=embed)
                self.now_playing_messages[guild_id] = msg
            except Exception:
                pass

        except Exception as e:
            embed = self._make_embed("❌ Playback Error", f"Could not play: {e}", BOT_ERROR_COLOR)
            try:
                await text_channel.send(embed=embed)
            except Exception:
                pass
            # Try next song
            await self._play_next(guild_id, text_channel)

    def _make_now_playing_embed(self, song: Song, queue: MusicQueue) -> discord.Embed:
        """Create a rich 'Now Playing' embed."""
        embed = discord.Embed(
            title="🎵 Now Playing",
            description=f"**[{song.title}]({song.url})**",
            color=BOT_COLOR
        )
        embed.add_field(name="⏱️ Duration", value=song.duration_str, inline=True)
        embed.add_field(name="🎧 Requested by", value=song.requester, inline=True)

        loop_icons = {LoopMode.OFF: "❌ Off", LoopMode.SINGLE: "🔂 Single", LoopMode.QUEUE: "🔁 Queue"}
        embed.add_field(name="🔄 Loop", value=loop_icons[queue.loop_mode], inline=True)

        if queue.size > 0:
            embed.add_field(name="📋 Queue", value=f"{queue.size} song(s)", inline=True)

        if song.thumbnail:
            embed.set_thumbnail(url=song.thumbnail)

        embed.timestamp = datetime.utcnow()
        embed.set_footer(text="Discord Music Bot")
        return embed

    # ──────────────────────────────────────────────
    #  Slash Commands
    # ──────────────────────────────────────────────

    async def _load_playlist_background(self, playlist_url: str, guild_id: int, requester_name: str, requester_id: int, text_channel):
        """Load a YouTube playlist/radio mix in the background and add songs to queue."""
        try:
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(playlist_url)
            params = parse_qs(parsed.query)
            current_video_id = params.get('v', [None])[0]

            # Use extract_flat to quickly get playlist entries (just titles + URLs, no stream URLs)
            playlist_opts = YTDL_FORMAT_OPTIONS.copy()
            playlist_opts["noplaylist"] = False
            playlist_opts["extract_flat"] = "in_playlist"

            ytdl_playlist = yt_dlp.YoutubeDL(playlist_opts)
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(
                None,
                functools.partial(ytdl_playlist.extract_info, playlist_url, download=False)
            )

            if not data or "entries" not in data:
                print(f"[PLAYLIST-BG] No entries found in playlist")
                return

            entries = [e for e in data["entries"] if e is not None]
            queue = self.get_queue(guild_id)
            added = 0

            for entry in entries:
                video_id = entry.get("id", entry.get("url", ""))
                # Skip the video that's already playing
                if video_id == current_video_id:
                    continue

                song = Song(
                    title=entry.get("title", "Unknown"),
                    url=f"https://www.youtube.com/watch?v={video_id}" if not entry.get("webpage_url") else entry.get("webpage_url"),
                    stream_url="",  # Will be fetched when it's time to play
                    duration=entry.get("duration", 0) or 0,
                    thumbnail=entry.get("thumbnail", entry.get("thumbnails", [{}])[0].get("url", "") if entry.get("thumbnails") else ""),
                    requester=requester_name,
                    requester_id=requester_id,
                )
                queue.add(song)
                added += 1

            if added > 0:
                playlist_title = data.get("title", "Playlist")
                print(f"[PLAYLIST-BG] Added {added} songs from '{playlist_title}' to queue")
                embed = discord.Embed(
                    title="📋 Playlist Loaded",
                    description=f"Added **{added}** songs from **{playlist_title}** to the queue!",
                    color=BOT_COLOR,
                )
                try:
                    await text_channel.send(embed=embed)
                except Exception:
                    pass

                # If bot is idle (not playing), start playing the next song
                guild = self.bot.get_guild(guild_id)
                if guild and guild.voice_client and not guild.voice_client.is_playing():
                    print(f"[PLAYLIST-BG] Bot is idle, triggering playback...")
                    await self._play_next(guild_id, text_channel)

        except Exception as e:
            print(f"[PLAYLIST-BG] Error loading playlist: {e}")

    @discord.slash_command(name="play", description="Play a song from YouTube (URL or search)")
    async def play(
        self,
        ctx: discord.ApplicationContext,
        query: discord.Option(str, "YouTube URL or search keywords", required=True),
    ):
        print(f"\n[PLAY] ──────────────────────────────────────────")
        print(f"[PLAY] 1. Received /play '{query}' from {ctx.author}")
        try:
            await ctx.defer()
            print(f"[PLAY] 2. Deferred response in Discord")

            vc = await self._ensure_voice(ctx, deferred=True)
            if not vc:
                print(f"[PLAY] 2.1 No voice client available, stopping.")
                return
            print(f"[PLAY] 3. In voice channel '{vc.channel.name}'")

            print(f"[PLAY] 4. Extracting song info via yt-dlp...")
            try:
                results = await YTDLSource.extract_info(query)
                print(f"[PLAY] 5. Extraction finished, {len(results)} item(s) found")
            except Exception as e:
                print(f"[PLAY] 5.1 Extraction error: {e}")
                embed = self._make_embed("❌ Error", f"Could not find anything: {e}", BOT_ERROR_COLOR)
                await ctx.followup.send(embed=embed)
                return

            if not results:
                print(f"[PLAY] 5.2 No results found.")
                embed = self._make_embed("❌ Not Found", "No results found for your query.", BOT_ERROR_COLOR)
                await ctx.followup.send(embed=embed)
                return

            queue = self.get_queue(ctx.guild_id)
            info = results[0]
            song = Song(
                title=info["title"],
                url=info["url"],
                stream_url=info["stream_url"],
                duration=info["duration"],
                thumbnail=info["thumbnail"],
                requester=ctx.author.display_name,
                requester_id=ctx.author.id,
            )

            # Check if bot should play immediately or add to queue
            if not vc.is_playing() and queue.is_empty:
                queue.current = song
                queue._history.append(song)
                print(f"[PLAY] 6. Queue is empty, playing immediately: {song.title}")

                if not song.stream_url:
                    print(f"[PLAY] 6.1 Stream URL missing, fetching stream URL...")
                    fresh = await YTDLSource.get_stream_url(song.url)
                    if fresh:
                        song.stream_url = fresh["stream_url"]

                volume = self.get_volume(ctx.guild_id)
                ffmpeg_opts = FFMPEG_OPTIONS.copy()
                ffmpeg_opts["options"] = f'-vn -bufsize 64k -filter:a "volume={volume}"'

                print(f"[PLAY] 7. Starting FFmpeg audio player...")
                source = discord.FFmpegPCMAudio(song.stream_url, executable=FFMPEG_PATH, **ffmpeg_opts)

                def after_playing(error):
                    if error:
                        print(f"[PLAYER] Error after playing: {error}")
                    asyncio.run_coroutine_threadsafe(
                        self._play_next(ctx.guild_id, ctx.channel),
                        self.bot.loop
                    )

                vc.play(source, after=after_playing)
                print(f"[PLAY] 8. Playback started, sending Now Playing embed...")

                embed = self._make_now_playing_embed(song, queue)
                await ctx.followup.send(embed=embed)
                print(f"[PLAY] 9. Embed sent successfully!")

                # If original URL had playlist params, load the rest in background
                from urllib.parse import urlparse, parse_qs
                orig_parsed = urlparse(query)
                orig_params = parse_qs(orig_parsed.query)
                if 'list' in orig_params or 'start_radio' in orig_params:
                    print(f"[PLAY] 10. Detected playlist URL, loading remaining songs in background...")
                    asyncio.create_task(
                        self._load_playlist_background(
                            query, ctx.guild_id,
                            ctx.author.display_name, ctx.author.id,
                            ctx.channel
                        )
                    )
            else:
                queue.add(song)
                print(f"[PLAY] 6. Added to queue: {song.title} (#{queue.size})")
                embed = self._make_embed(
                    "✅ Added to Queue",
                    f"**[{song.title}]({song.url})**\n"
                    f"⏱️ Duration: {song.duration_str} | 📋 Position: #{queue.size}"
                )
                if song.thumbnail:
                    embed.set_thumbnail(url=song.thumbnail)
                await ctx.followup.send(embed=embed)
                print(f"[PLAY] 7. Queue embed sent successfully!")

        except Exception as e:
            print(f"[PLAY] Unexpected error during /play: {e}")
            import traceback
            traceback.print_exc()
            embed = self._make_embed("❌ Error", f"An error occurred: {e}", BOT_ERROR_COLOR)
            try:
                await ctx.followup.send(embed=embed)
            except Exception:
                pass

    @discord.slash_command(name="search", description="Search YouTube and choose a song")
    async def search(
        self,
        ctx: discord.ApplicationContext,
        query: discord.Option(str, "Search keywords", required=True),
    ):
        await ctx.defer()

        vc = await self._ensure_voice(ctx, deferred=True)
        if not vc:
            return

        try:
            results = await YTDLSource.extract_info(query)
        except Exception as e:
            embed = self._make_embed("❌ Error", str(e), BOT_ERROR_COLOR)
            await ctx.followup.send(embed=embed)
            return

        if not results:
            embed = self._make_embed("❌ Not Found", "No results found.", BOT_ERROR_COLOR)
            await ctx.followup.send(embed=embed)
            return

        # Build selection embed
        description_lines = []
        for i, r in enumerate(results[:5]):
            dur = Song(r["title"], r["url"], "", r["duration"], "", "", 0).duration_str
            description_lines.append(f"**{i+1}.** [{r['title']}]({r['url']}) `{dur}`")

        embed = self._make_embed(
            "🔍 Search Results",
            "\n\n".join(description_lines) + "\n\n*Choose a number (1-5) or type `cancel`*"
        )
        await ctx.followup.send(embed=embed)

        # Wait for user response
        def check(m):
            return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id

        try:
            msg = await self.bot.wait_for("message", check=check, timeout=30)
            if msg.content.lower() == "cancel":
                await ctx.channel.send(embed=self._make_embed("❌ Cancelled", "Search cancelled."))
                return

            try:
                choice = int(msg.content) - 1
                if 0 <= choice < len(results):
                    info = results[choice]
                    song = Song(
                        title=info["title"],
                        url=info["url"],
                        stream_url=info["stream_url"],
                        duration=info["duration"],
                        thumbnail=info["thumbnail"],
                        requester=ctx.author.display_name,
                        requester_id=ctx.author.id,
                    )

                    queue = self.get_queue(ctx.guild_id)
                    if not vc.is_playing() and queue.is_empty:
                        queue.current = song
                        fresh = await YTDLSource.get_stream_url(song.url)
                        if fresh:
                            song.stream_url = fresh["stream_url"]

                        volume = self.get_volume(ctx.guild_id)
                        ffmpeg_opts = FFMPEG_OPTIONS.copy()
                        ffmpeg_opts["options"] = f'-vn -bufsize 64k -filter:a "volume={volume}"'
                        source = discord.FFmpegPCMAudio(song.stream_url, executable=FFMPEG_PATH, **ffmpeg_opts)

                        def after_playing(error):
                            asyncio.run_coroutine_threadsafe(
                                self._play_next(ctx.guild_id, ctx.channel),
                                self.bot.loop
                            )

                        vc.play(source, after=after_playing)
                        embed = self._make_now_playing_embed(song, queue)
                        await ctx.channel.send(embed=embed)
                    else:
                        queue.add(song)
                        embed = self._make_embed(
                            "✅ Added to Queue",
                            f"**[{song.title}]({song.url})**\n⏱️ {song.duration_str} | 📋 #{queue.size}"
                        )
                        await ctx.channel.send(embed=embed)
                else:
                    await ctx.channel.send(embed=self._make_embed("❌ Invalid", "Invalid choice.", BOT_ERROR_COLOR))
            except ValueError:
                await ctx.channel.send(embed=self._make_embed("❌ Invalid", "Please enter a number.", BOT_ERROR_COLOR))
        except asyncio.TimeoutError:
            await ctx.channel.send(embed=self._make_embed("⏰ Timeout", "Search timed out.", BOT_WARN_COLOR))

    @discord.slash_command(name="pause", description="Pause the current song")
    async def pause(self, ctx: discord.ApplicationContext):
        if not ctx.voice_client or not ctx.voice_client.is_playing():
            embed = self._make_embed("❌ Error", "Nothing is playing!", BOT_ERROR_COLOR)
            await ctx.respond(embed=embed, ephemeral=True)
            return

        ctx.voice_client.pause()
        embed = self._make_embed("⏸️ Paused", "Music paused. Use `/resume` to continue.")
        await ctx.respond(embed=embed)

    @discord.slash_command(name="resume", description="Resume the paused song")
    async def resume(self, ctx: discord.ApplicationContext):
        if not ctx.voice_client or not ctx.voice_client.is_paused():
            embed = self._make_embed("❌ Error", "Nothing is paused!", BOT_ERROR_COLOR)
            await ctx.respond(embed=embed, ephemeral=True)
            return

        ctx.voice_client.resume()
        embed = self._make_embed("▶️ Resumed", "Music resumed!")
        await ctx.respond(embed=embed)

    @discord.slash_command(name="skip", description="Skip the current song")
    async def skip(self, ctx: discord.ApplicationContext):
        if not ctx.voice_client or not ctx.voice_client.is_playing():
            embed = self._make_embed("❌ Error", "Nothing is playing!", BOT_ERROR_COLOR)
            await ctx.respond(embed=embed, ephemeral=True)
            return

        queue = self.get_queue(ctx.guild_id)
        current = queue.current
        title = current.title if current else "Unknown"

        ctx.voice_client.stop()  # This triggers after_playing -> _play_next
        embed = self._make_embed("⏭️ Skipped", f"Skipped **{title}**")
        await ctx.respond(embed=embed)

    @discord.slash_command(name="stop", description="Stop playing and clear the queue")
    async def stop(self, ctx: discord.ApplicationContext):
        if not ctx.voice_client:
            embed = self._make_embed("❌ Error", "Bot is not in a voice channel!", BOT_ERROR_COLOR)
            await ctx.respond(embed=embed, ephemeral=True)
            return

        queue = self.get_queue(ctx.guild_id)
        queue.clear_all()

        ctx.voice_client.stop()
        await ctx.voice_client.disconnect()

        embed = self._make_embed("⏹️ Stopped", "Music stopped and queue cleared. Goodbye! 👋")
        await ctx.respond(embed=embed)

    @discord.slash_command(name="queue", description="Show the current queue")
    async def queue(self, ctx: discord.ApplicationContext):
        queue = self.get_queue(ctx.guild_id)

        if queue.current is None and queue.is_empty:
            embed = self._make_embed("📋 Queue", "The queue is empty! Use `/play` to add songs.")
            await ctx.respond(embed=embed)
            return

        description = ""
        if queue.current:
            description += f"**🎵 Now Playing:**\n[{queue.current.title}]({queue.current.url}) `{queue.current.duration_str}`\n"
            description += f"Requested by: {queue.current.requester}\n\n"

        if not queue.is_empty:
            description += "**📋 Up Next:**\n"
            songs = queue.queue_list
            # Show first 10 songs
            for i, song in enumerate(songs[:10]):
                description += f"`{i+1}.` [{song.title}]({song.url}) `{song.duration_str}`\n"

            if len(songs) > 10:
                description += f"\n*... and {len(songs) - 10} more songs*\n"

            # Total duration
            total_dur = queue.total_duration
            hours, remainder = divmod(total_dur, 3600)
            minutes, seconds = divmod(remainder, 60)
            if hours:
                dur_str = f"{hours}h {minutes}m"
            else:
                dur_str = f"{minutes}m {seconds}s"
            description += f"\n**Total:** {queue.size} songs | ⏱️ {dur_str}"

        loop_icons = {LoopMode.OFF: "❌ Off", LoopMode.SINGLE: "🔂 Single", LoopMode.QUEUE: "🔁 Queue"}
        description += f"\n**Loop:** {loop_icons[queue.loop_mode]}"

        embed = self._make_embed("📋 Music Queue", description)
        await ctx.respond(embed=embed)

    @discord.slash_command(name="nowplaying", description="Show info about the current song")
    async def nowplaying(self, ctx: discord.ApplicationContext):
        queue = self.get_queue(ctx.guild_id)
        if not queue.current:
            embed = self._make_embed("❌ Error", "Nothing is playing right now!", BOT_ERROR_COLOR)
            await ctx.respond(embed=embed, ephemeral=True)
            return

        embed = self._make_now_playing_embed(queue.current, queue)
        await ctx.respond(embed=embed)

    @discord.slash_command(name="volume", description="Set the volume (0-100)")
    async def volume(
        self,
        ctx: discord.ApplicationContext,
        level: discord.Option(int, "Volume level (0-100)", required=True, min_value=0, max_value=100),
    ):
        self.volumes[ctx.guild_id] = level / 100

        vol_bar = "█" * (level // 10) + "░" * (10 - level // 10)
        embed = self._make_embed("🔊 Volume", f"`{vol_bar}` **{level}%**")

        # If something is playing, we need to restart with new volume
        # (FFmpeg volume filter is set at start, can't change mid-stream without PCMVolumeTransformer)
        if ctx.voice_client and ctx.voice_client.is_playing():
            embed.set_footer(text="Volume change will apply to the next song")

        await ctx.respond(embed=embed)

    @discord.slash_command(name="loop", description="Toggle loop mode (Off → Single → Queue)")
    async def loop(self, ctx: discord.ApplicationContext):
        queue = self.get_queue(ctx.guild_id)
        mode = queue.cycle_loop()

        icons = {
            LoopMode.OFF: ("❌ Loop Off", "Looping disabled."),
            LoopMode.SINGLE: ("🔂 Loop Single", "Current song will repeat."),
            LoopMode.QUEUE: ("🔁 Loop Queue", "The entire queue will repeat."),
        }

        title, desc = icons[mode]
        embed = self._make_embed(title, desc)
        await ctx.respond(embed=embed)

    @discord.slash_command(name="shuffle", description="Shuffle the queue")
    async def shuffle(self, ctx: discord.ApplicationContext):
        queue = self.get_queue(ctx.guild_id)
        if queue.is_empty:
            embed = self._make_embed("❌ Error", "Queue is empty!", BOT_ERROR_COLOR)
            await ctx.respond(embed=embed, ephemeral=True)
            return

        queue.shuffle()
        embed = self._make_embed("🔀 Shuffled", f"Shuffled **{queue.size}** songs in the queue!")
        await ctx.respond(embed=embed)

    @discord.slash_command(name="remove", description="Remove a song from the queue")
    async def remove(
        self,
        ctx: discord.ApplicationContext,
        position: discord.Option(int, "Position in queue (1-based)", required=True, min_value=1),
    ):
        queue = self.get_queue(ctx.guild_id)
        song = queue.remove(position - 1)

        if not song:
            embed = self._make_embed("❌ Error", f"No song at position {position}.", BOT_ERROR_COLOR)
            await ctx.respond(embed=embed, ephemeral=True)
            return

        embed = self._make_embed("🗑️ Removed", f"Removed **{song.title}** from the queue.")
        await ctx.respond(embed=embed)

    @discord.slash_command(name="clear", description="Clear the queue")
    async def clear(self, ctx: discord.ApplicationContext):
        queue = self.get_queue(ctx.guild_id)
        count = queue.size
        queue.clear()

        embed = self._make_embed("🗑️ Queue Cleared", f"Removed **{count}** songs from the queue.")
        await ctx.respond(embed=embed)

    @discord.slash_command(name="lyrics", description="Get lyrics for the current song")
    async def lyrics(
        self,
        ctx: discord.ApplicationContext,
        query: discord.Option(str, "Song name (optional, uses current song)", required=False, default=None),
    ):
        await ctx.defer()

        queue = self.get_queue(ctx.guild_id)
        search_title = query

        if not search_title:
            if not queue.current:
                embed = self._make_embed("❌ Error", "Nothing playing and no query provided!", BOT_ERROR_COLOR)
                await ctx.followup.send(embed=embed)
                return
            search_title = queue.current.title

        lyrics_text = await fetch_lyrics(search_title, genius_token=GENIUS_API_TOKEN)

        if not lyrics_text:
            embed = self._make_embed(
                "❌ Lyrics Not Found",
                f"Could not find lyrics for: **{search_title}**\n\n"
                "Try using `/lyrics` with a more specific song name.",
                BOT_ERROR_COLOR
            )
            await ctx.followup.send(embed=embed)
            return

        embed = self._make_embed("📝 Lyrics", "")
        embed.add_field(name=search_title, value=lyrics_text[:1024], inline=False)

        # If lyrics is longer than 1024, add more fields
        if len(lyrics_text) > 1024:
            remaining = lyrics_text[1024:]
            chunks = [remaining[i:i+1024] for i in range(0, len(remaining), 1024)]
            for chunk in chunks[:3]:  # Max 3 extra fields
                embed.add_field(name="\u200b", value=chunk, inline=False)

        await ctx.followup.send(embed=embed)

    @discord.slash_command(name="move", description="Move a song in the queue")
    async def move(
        self,
        ctx: discord.ApplicationContext,
        from_pos: discord.Option(int, "Current position", required=True, min_value=1),
        to_pos: discord.Option(int, "New position", required=True, min_value=1),
    ):
        queue = self.get_queue(ctx.guild_id)
        success = queue.move(from_pos - 1, to_pos - 1)

        if not success:
            embed = self._make_embed("❌ Error", "Invalid positions!", BOT_ERROR_COLOR)
            await ctx.respond(embed=embed, ephemeral=True)
            return

        songs = queue.queue_list
        moved_title = songs[to_pos - 1].title if to_pos - 1 < len(songs) else "Unknown"
        embed = self._make_embed("↕️ Moved", f"Moved **{moved_title}** to position #{to_pos}")
        await ctx.respond(embed=embed)

    # ──────────────────────────────────────────────
    #  Event Listeners
    # ──────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Auto-disconnect if bot is alone in voice channel."""
        if member.bot:
            return

        if before.channel and not after.channel:
            # Someone left a voice channel
            guild = before.channel.guild
            if guild.voice_client and guild.voice_client.channel == before.channel:
                # Check if bot is alone
                members = [m for m in before.channel.members if not m.bot]
                if len(members) == 0:
                    await asyncio.sleep(30)  # Wait 30s before leaving
                    # Re-check
                    if guild.voice_client and guild.voice_client.channel == before.channel:
                        members = [m for m in before.channel.members if not m.bot]
                        if len(members) == 0:
                            self.get_queue(guild.id).clear_all()
                            guild.voice_client.stop()
                            await guild.voice_client.disconnect()


def setup(bot: commands.Bot):
    bot.add_cog(Music(bot))



