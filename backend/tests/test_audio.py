from app.audio import AudioBucketer, pcm_to_wav


def test_bucketer_emits_overlapping_windows_every_hop():
    bucketer = AudioBucketer(sample_rate=16_000, window_seconds=30, hop_seconds=15)
    chunks = bucketer.feed(b"\0\0" * (16_000 * 61))
    assert [(chunk.start_seconds, chunk.end_seconds) for chunk in chunks] == [
        (0, 15), (0, 30), (15, 45), (30, 60),
    ]
    # First reading fires at just one hop of audio -- clamped to start at 0 --
    # not a full window, so a short check-in still gets scored quickly.
    assert len(chunks[0].pcm) == 16_000 * 15 * 2
    # From the second reading on, every window is full-length, each overlapping
    # the previous by window_seconds - hop_seconds = 15s.
    assert len(chunks[1].pcm) == 16_000 * 30 * 2


def test_flush_skips_a_clip_that_never_reached_a_full_window():
    bucketer = AudioBucketer(sample_rate=16_000, window_seconds=30, hop_seconds=15, min_tail_seconds=16)
    bucketer.feed(b"\0\0" * (16_000 * 10))  # 10s total -- never crosses the first 15s hop
    assert bucketer.flush() == []


def test_flush_adds_a_final_window_when_new_content_is_worth_it():
    bucketer = AudioBucketer(sample_rate=16_000, window_seconds=30, hop_seconds=15)
    bucketer.feed(b"\0\0" * (16_000 * 53))  # 3 hops fired (ending at 45s); 8s of new content since
    chunks = bucketer.flush()
    assert len(chunks) == 1
    assert (chunks[0].start_seconds, chunks[0].end_seconds) == (23, 53)


def test_flush_skips_a_negligible_trailing_remainder():
    bucketer = AudioBucketer(sample_rate=16_000, window_seconds=30, hop_seconds=15)
    bucketer.feed(b"\0\0" * (16_000 * 46))  # 3 hops fired (ending at 45s); only 1s of new content since
    assert bucketer.flush() == []


def test_pcm_is_packaged_as_a_wav():
    wav = pcm_to_wav(b"\0\0" * 16_000, 16_000)
    assert wav[:4] == b"RIFF"
    assert b"WAVE" in wav[:16]
