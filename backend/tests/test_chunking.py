from app.chunking import chunk_transcript

SAMPLE = """## Transcript

Lenny (00:00:00):
Welcome to the show. Tell us about growth.

Guest (00:00:10):
""" + ("We tested onboarding ideas every week. " * 60) + """

Lenny (00:02:00):
And what happened next?

Guest (00:02:05):
""" + ("Retention improved a lot. " * 60)


def test_chunks_have_timestamps_and_speakers():
    chunks = chunk_transcript(SAMPLE)
    assert len(chunks) >= 2
    assert chunks[0].start_ts == "00:00:00"
    assert chunks[0].text.startswith("Lenny:")


def test_chunks_are_bounded():
    for c in chunk_transcript(SAMPLE):
        assert len(c.text.split()) <= 700


def test_overlap_between_chunks():
    chunks = chunk_transcript(SAMPLE)
    last_line_of_first = chunks[0].text.splitlines()[-1]
    assert last_line_of_first in chunks[1].text


def test_empty_body():
    assert chunk_transcript("## Transcript\n") == []


def test_transcript_without_timestamps():
    body = "## Transcript\n\nAdriel Frederick:\nHello there friend.\n\nLenny:\nWelcome to the show.\n"
    chunks = chunk_transcript(body)
    assert len(chunks) == 1
    assert chunks[0].start_ts == ""
    assert "Lenny: Welcome" in chunks[0].text


def test_short_timestamps_and_bare_continuation():
    body = "## Transcript\n\nTeresa (00:02):\nFirst part.\n\n(00:13):\nSecond part, same speaker.\n"
    chunks = chunk_transcript(body)
    assert chunks[0].start_ts == "00:00:02"
    assert "Teresa: Second part" in chunks[0].text


def test_inline_bracket_format():
    body = "## Transcript\n\n[00:00:00] Ryan: Hello there.\n[00:00:28] Lenny: Welcome.\n"
    chunks = chunk_transcript(body)
    assert chunks and chunks[0].start_ts == "00:00:00"
    assert "Lenny: Welcome." in chunks[0].text
