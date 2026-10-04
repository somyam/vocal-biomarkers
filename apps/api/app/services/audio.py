import io
import wave
from dataclasses import dataclass


@dataclass
class AudioChunk:
    index: int
    pcm: bytes
    start_seconds: float
    end_seconds: float
    sample_rate: int = 16000

    @property
    def wav_bytes(self) -> bytes:
        return pcm_to_wav(self.pcm, self.sample_rate)


def pcm_to_wav(pcm: bytes, sample_rate: int = 16000) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return out.getvalue()


class AudioBucketer:
    """Overlapping PCM windows: a new `window_seconds`-long reading every
    `hop_seconds`, so consecutive readings share `window_seconds - hop_seconds`
    of audio rather than reset cleanly at a hard boundary. A signal that happens
    to spike right at a cut gets caught by the next window too, instead of being
    split across two uncorrelated readings -- ported from clinical_agent's own
    live AudioBucketer (`window_s=30, hop_s=15`). Unlike that one, this only
    ever returns ready chunks for the caller to queue; nothing here blocks on
    processing them, so streaming.py's fire-and-forget task queue needed no
    changes at all to pick this up.

    During ramp-up (before a full window's worth of audio exists) each window
    is clamped to start at 0, so the very first reading fires at `hop_seconds`
    total audio -- 15s by default, exactly Amplifier's own documented floor --
    rather than needing a full 30s before anything gets scored at all.

    Save preserves the complete recording but submits no off-cadence window.
    Only scheduled hop boundaries produce analysis jobs.
    """
    def __init__(self, sample_rate: int = 16000, window_seconds: float = 30.0,
                 hop_seconds: float = 15.0):
        self.sample_rate = sample_rate
        self.window_seconds = window_seconds
        self.hop_seconds = hop_seconds
        self.buffer = bytearray()
        self.hops = 0  # hop boundaries already emitted
        self.index = 0

    @property
    def seconds(self) -> float:
        return len(self.buffer) / (self.sample_rate * 2)

    def _window(self, start_seconds: float, end_seconds: float) -> AudioChunk:
        a = round(start_seconds * self.sample_rate) * 2
        b = round(end_seconds * self.sample_rate) * 2
        self.index += 1
        return AudioChunk(self.index, bytes(self.buffer[a:b]),
                          round(start_seconds, 2), round(end_seconds, 2), self.sample_rate)

    def feed(self, pcm: bytes) -> list[AudioChunk]:
        self.buffer.extend(pcm)
        ready: list[AudioChunk] = []
        while self.seconds >= (self.hops + 1) * self.hop_seconds:
            self.hops += 1
            end = self.hops * self.hop_seconds
            ready.append(self._window(max(0.0, end - self.window_seconds), end))
        return ready

    def flush(self) -> list[AudioChunk]:
        """No extra analysis on Save: feed() already emitted every scheduled hop."""
        return []
