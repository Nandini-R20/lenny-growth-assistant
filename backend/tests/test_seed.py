import gzip
import json

import pytest

import app.seed as seed
from app.config import settings


def test_vector_packing_roundtrip_is_lossless_float32():
    vec_text = "[0.5,-1.25,3.0,0.0001]"
    back = seed.unpack_vector(seed.pack_vector(vec_text))
    assert [round(x, 6) for x in back] == [0.5, -1.25, 3.0, 0.0001]


def test_import_refuses_a_seed_from_a_different_embedding_model(tmp_path):
    p = tmp_path / "x.jsonl.gz"
    with gzip.open(p, "wt") as f:
        f.write(json.dumps({"type": "meta", "version": 1, "model": "some-other-model", "dim": 999}) + "\n")
    with pytest.raises(seed.SeedError, match="Re-run ingestion"):
        seed.import_seed(p)


def test_missing_seed_file_is_a_clear_error(tmp_path):
    with pytest.raises(seed.SeedError, match="not found"):
        seed.import_seed(tmp_path / "nope.jsonl.gz")


def test_seed_is_skipped_when_index_already_exists(monkeypatch, tmp_path):
    f = tmp_path / "s.jsonl.gz"
    f.write_bytes(b"")
    monkeypatch.setattr(settings, "seed_path", str(f))
    monkeypatch.setattr(seed, "_count_episodes", lambda: 82)
    monkeypatch.setattr(seed, "import_seed", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not import")))
    assert seed.seed_if_empty() is None
