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

    `flush()` uses two separate thresholds, not one. The loop invariant above
    guarantees "audio since the last emitted window" is always strictly less
    than `hop_seconds` -- so a single threshold set >= hop_seconds (as
    clinical_agent's own `min_s == hop_s` config does) can never be cleared,
    ever, regardless of how much audio actually exists; that flush() path is
    silently dead code there, just never noticed because clinical visits are
    long enough that the tail rarely matters. It matters a lot for a short
    check-in, so: `min_tail_seconds` gates the case where no window has fired
    yet at all (the whole clip has to clear Amplifier's real floor on its own
    -- there's no audio to borrow from a previous window); `min_new_tail_seconds`
    gates the case where at least one window already fired (a final window
    would mostly re-score audio already read, so only bother if the genuinely
    new part is still meaningful)."""
    def __init__(self, sample_rate: int = 16000, window_seconds: float = 30.0,
                 hop_seconds: float = 15.0, min_tail_seconds: float = 16.0,
                 min_new_tail_seconds: float | None = None,
                 minimum_tail_seconds: float | None = None):
        self.sample_rate = sample_rate
        self.window_seconds = window_seconds
        self.hop_seconds = hop_seconds
        self.min_tail_seconds = minimum_tail_seconds if minimum_tail_seconds is not None else min_tail_seconds
        self.min_new_tail_seconds = hop_seconds / 2 if min_new_tail_seconds is None else min_new_tail_seconds
        self.buffer = bytearray()
        self.hops = 0  # hop boundaries already emitted
        self.index = 0

    @property
    def seconds(self) -> float:
        return len(self.buffer) / (self.sample_rate * 2)

    def _window(self, start_seconds: float, end_seconds: float) -> AudioChunk:
        a = int(start_seconds * self.sample_rate) * 2
        b = int(end_seconds * self.sample_rate) * 2
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
        end = self.seconds
        if self.hops == 0:
            # Never crossed a full hop: no prior window to lean on, so the whole
            # clip has to clear the real floor by itself.
            if end < self.min_tail_seconds:
                return []
            return [self._window(0.0, end)]
        # At least one window already fired -- only worth a final, mostly
        # redundant read if the genuinely new content since then is meaningful.
        if end - self.hops * self.hop_seconds < self.min_new_tail_seconds:
            return []
        return [self._window(max(0.0, end - self.window_seconds), end)]
