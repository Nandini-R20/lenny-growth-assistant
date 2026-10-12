import pytest

from app.retrieval import Hit


def make_hit(i=1, sim=0.82, ts="00:10:00", text="We hired our first head of growth after product-market fit."):
    return Hit(chunk_id=i, slug=f"ep-{i}", guest=f"Guest {i}", title=f"Episode {i}",
               youtube_url=f"https://www.youtube.com/watch?v=abc{i}", start_ts=ts, content=text, similarity=sim)


class FakeAgent:
    """Stands in for the Pi subprocess so API tests are fast and deterministic."""
    calls: list = []

    def __init__(self, script=None, error=None):
        self.script, self.error = script or ["A grounded answer [1]."], error

    def stream(self, provider, message):
        FakeAgent.calls.append((provider, message))
        for part in self.script:
            yield part
        if self.error:
            raise self.error


@pytest.fixture
def hit():
    return make_hit
