from app.audio import AudioBucketer, pcm_to_wav


def test_bucketer_emits_non_overlapping_30_second_windows():
    bucketer = AudioBucketer(sample_rate=16_000, window_seconds=30)
    chunks = bucketer.feed(b"\0\0" * (16_000 * 61))
    assert [(chunk.start_seconds, chunk.end_seconds) for chunk in chunks] == [(0, 30), (30, 60)]
    assert len(chunks[0].pcm) == 16_000 * 30 * 2


def test_flush_keeps_a_tail_that_is_long_enough_for_pulse():
    bucketer = AudioBucketer(sample_rate=16_000, window_seconds=30, minimum_tail_seconds=20)
    bucketer.feed(b"\0\0" * (16_000 * 51))
    chunks = bucketer.flush()
    assert len(chunks) == 1
    assert (chunks[0].start_seconds, chunks[0].end_seconds) == (30, 51)


def test_pcm_is_packaged_as_a_wav():
    wav = pcm_to_wav(b"\0\0" * 16_000, 16_000)
    assert wav[:4] == b"RIFF"
    assert b"WAVE" in wav[:16]
