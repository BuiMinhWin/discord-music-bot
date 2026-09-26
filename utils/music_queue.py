import asyncio
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class LoopMode(Enum):
    OFF = "off"
    SINGLE = "single"
    QUEUE = "queue"


@dataclass
class Song:
    """Represents a song in the queue."""
    title: str
    url: str
    stream_url: str
    duration: int  # seconds
    thumbnail: str
    requester: str  # user display name
    requester_id: int

    @property
    def duration_str(self) -> str:
        """Format duration as MM:SS or HH:MM:SS."""
        if self.duration <= 0:
            return "LIVE"
        hours, remainder = divmod(self.duration, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"


class MusicQueue:
    """Manages the music queue for a guild."""

    def __init__(self, max_size: int = 500):
        self._queue: list[Song] = []
        self._history: list[Song] = []
        self._current: Optional[Song] = None
        self._loop_mode: LoopMode = LoopMode.OFF
        self._max_size = max_size

    @property
    def current(self) -> Optional[Song]:
        return self._current

    @current.setter
    def current(self, song: Optional[Song]):
        self._current = song

    @property
    def loop_mode(self) -> LoopMode:
        return self._loop_mode

    @loop_mode.setter
    def loop_mode(self, mode: LoopMode):
        self._loop_mode = mode

    @property
    def is_empty(self) -> bool:
        return len(self._queue) == 0

    @property
    def size(self) -> int:
        return len(self._queue)

    @property
    def queue_list(self) -> list[Song]:
        return self._queue.copy()

    @property
    def total_duration(self) -> int:
        return sum(s.duration for s in self._queue if s.duration > 0)

    def add(self, song: Song) -> bool:
        """Add a song to the queue. Returns False if queue is full."""
        if len(self._queue) >= self._max_size:
            return False
        self._queue.append(song)
        return True

    def add_many(self, songs: list[Song]) -> int:
        """Add multiple songs. Returns how many were added."""
        space = self._max_size - len(self._queue)
        to_add = songs[:space]
        self._queue.extend(to_add)
        return len(to_add)

    def next(self) -> Optional[Song]:
        """Get the next song based on loop mode."""
        if self._current:
            self._history.append(self._current)

        if self._loop_mode == LoopMode.SINGLE and self._current:
            return self._current

        if self._loop_mode == LoopMode.QUEUE and self._current:
            self._queue.append(self._current)

        if not self._queue:
            self._current = None
            return None

        self._current = self._queue.pop(0)
        return self._current

    def skip(self) -> Optional[Song]:
        """Skip current song (ignores SINGLE loop)."""
        if self._current:
            self._history.append(self._current)

        if self._loop_mode == LoopMode.QUEUE and self._current:
            self._queue.append(self._current)

        if not self._queue:
            self._current = None
            return None

        self._current = self._queue.pop(0)
        return self._current

    def shuffle(self):
        """Shuffle the queue."""
        random.shuffle(self._queue)

    def remove(self, index: int) -> Optional[Song]:
        """Remove a song at index (0-based). Returns removed song or None."""
        if 0 <= index < len(self._queue):
            return self._queue.pop(index)
        return None

    def move(self, from_idx: int, to_idx: int) -> bool:
        """Move a song from one position to another."""
        if not (0 <= from_idx < len(self._queue) and 0 <= to_idx < len(self._queue)):
            return False
        song = self._queue.pop(from_idx)
        self._queue.insert(to_idx, song)
        return True

    def clear(self):
        """Clear the queue (keeps current song playing)."""
        self._queue.clear()

    def clear_all(self):
        """Clear everything including current."""
        self._queue.clear()
        self._history.clear()
        self._current = None
        self._loop_mode = LoopMode.OFF

    def cycle_loop(self) -> LoopMode:
        """Cycle through loop modes: OFF -> SINGLE -> QUEUE -> OFF."""
        modes = [LoopMode.OFF, LoopMode.SINGLE, LoopMode.QUEUE]
        current_idx = modes.index(self._loop_mode)
        self._loop_mode = modes[(current_idx + 1) % len(modes)]
        return self._loop_mode
