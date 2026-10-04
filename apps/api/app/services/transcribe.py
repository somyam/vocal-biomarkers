"""Local speech-to-text for a check-in's own recording. No audio leaves the server for
this step (faster-whisper runs in-process) — the same privacy stance as everything else
in this backend. Model weights download on first real use and are cached on disk inside
the container; expect the first non-mock transcription after a fresh build to be slower.
"""
import asyncio
import tempfile
from functools import lru_cache

from ..core.config import settings


class Transcriber:
    def __init__(self, model_size: str = "base", mock: bool = False):
        self.model_size = model_size
        self.mock = mock
        self._model = None

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel  # lazy: not imported at all in mock mode
            self._model = WhisperModel(self.model_size, compute_type="int8")
        return self._model

    def _run(self, wav_bytes: bytes) -> str:
        model = self._load()
        with tempfile.NamedTemporaryFile(suffix=".wav") as f:
            f.write(wav_bytes)
            f.flush()
            segments, _info = model.transcribe(f.name)
            return " ".join(s.text.strip() for s in segments).strip()

    async def transcribe(self, wav_bytes: bytes) -> str:
        if self.mock:
            return "[mock transcript]"
        return await asyncio.to_thread(self._run, wav_bytes)

    def warm_up(self) -> None:
        """Pays CTranslate2's first-inference cost (model construction plus a throwaway
        transcribe call) up front, at process startup, instead of on whichever user's
        check-in happens to be the first live stream to hit this process -- that first
        call is otherwise ~10s slower than every one after it, regardless of clip length."""
        if self.mock:
            return
        silence = b"\x00\x00" * 16_000  # 1s of silent 16kHz PCM, just to exercise the model
        from .audio import pcm_to_wav
        self._run(pcm_to_wav(silence))


@lru_cache
def transcriber() -> Transcriber:
    """One model instance per process, loaded on first real (non-mock) use and reused
    for every later check-in — reloading it per request would be needlessly slow."""
    return Transcriber(settings().whisper_model, mock=settings().mock_whisper)
