import io
import wave

import pytest

from app.services.audio import AudioBucketer, pcm_to_wav


@pytest.mark.parametrize("seconds,count", [(14, 0), (15, 1), (30, 2), (45, 3), (60, 4)])
def test_bucketer_emits_exact_overlapping_wav_windows(seconds, count):
    bucketer = AudioBucketer()
    # Distinct samples in each second detect incorrect slicing, not just lengths.
    pcm = b"".join(second.to_bytes(2, "little") * 16_000 for second in range(seconds))
    chunks = []
    # Arbitrary frame sizes must not change the schedule.
    for offset in range(0, len(pcm), 4096):
        chunks.extend(bucketer.feed(pcm[offset:offset + 4096]))
    expected = [(0, 15), (0, 30), (15, 45), (30, 60)][:count]
    assert [(c.start_seconds, c.end_seconds) for c in chunks] == expected
    for chunk, (start, end) in zip(chunks, expected):
        with wave.open(io.BytesIO(chunk.wav_bytes)) as wav:
            assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (16000, 1, 2)
            assert wav.getnframes() == (end - start) * 16000
            assert wav.readframes(wav.getnframes()) == pcm[start * 32000:end * 32000]


@pytest.mark.parametrize("seconds", [10, 14.999, 15, 20, 30, 46, 53, 60, 60.001])
def test_save_never_submits_an_off_cadence_window(seconds):
    bucketer = AudioBucketer()
    chunks = bucketer.feed(b"\0\0" * round(16_000 * seconds))
    assert len(chunks) == int(seconds // 15)
    assert bucketer.flush() == []
    assert bucketer.flush() == []


def test_pcm_is_packaged_as_a_wav():
    wav = pcm_to_wav(b"\0\0" * 16_000)
    assert wav[:4] == b"RIFF"
    assert b"WAVE" in wav[:16]
