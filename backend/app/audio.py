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
    """Non-overlapping 30-second PCM windows for a one-minute personal check-in."""
    def __init__(self, sample_rate: int = 16000, window_seconds: int = 30,
                 min_tail_seconds: int = 20, minimum_tail_seconds: int | None = None):
        self.sample_rate = sample_rate
        self.window_seconds = window_seconds
        self.min_tail_seconds = minimum_tail_seconds or min_tail_seconds
        self.buffer = bytearray()
        self.emitted = 0
        self.index = 0

    @property
    def seconds(self) -> float:
        return len(self.buffer) / (self.sample_rate * 2)

    def feed(self, pcm: bytes) -> list[AudioChunk]:
        self.buffer.extend(pcm)
        ready: list[AudioChunk] = []
        window_bytes = self.window_seconds * self.sample_rate * 2
        while len(self.buffer) - self.emitted >= window_bytes:
            start = self.emitted
            self.emitted += window_bytes
            self.index += 1
            ready.append(AudioChunk(self.index, bytes(self.buffer[start:self.emitted]), start / (self.sample_rate * 2), self.emitted / (self.sample_rate * 2), self.sample_rate))
        return ready

    def flush(self) -> list[AudioChunk]:
        remaining = len(self.buffer) - self.emitted
        if remaining < self.min_tail_seconds * self.sample_rate * 2:
            return []
        start = self.emitted
        self.emitted = len(self.buffer)
        self.index += 1
        return [AudioChunk(self.index, bytes(self.buffer[start:self.emitted]), start / (self.sample_rate * 2), self.seconds, self.sample_rate)]
