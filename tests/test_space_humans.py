import json
from pathlib import Path

from transithub.space.humans import HumansInSpace, HumansInSpaceClient

FIX = Path(__file__).parent / "fixtures"


def _fetch(url):
    return json.loads((FIX / "astros_sample.json").read_text())


def test_parses_total_and_by_craft():
    snap = HumansInSpaceClient(fetcher=_fetch).fetch()
    assert isinstance(snap, HumansInSpace)
    assert snap.total == 12
    assert snap.by_craft == {"ISS": 9, "Tiangong": 3}
    # crafts ordered by crew size, largest first
    assert snap.crafts == ["ISS", "Tiangong"]


def test_falls_back_to_summed_count_when_number_missing():
    def fetch(url):
        return {"people": [{"name": "A", "craft": "ISS"}, {"name": "B", "craft": "ISS"}]}
    snap = HumansInSpaceClient(fetcher=fetch).fetch()
    assert snap.total == 2 and snap.by_craft == {"ISS": 2}


def test_tries_each_url_until_one_succeeds():
    seen = []

    def fetch(url):
        seen.append(url)
        if url.startswith("https://"):
            raise OSError("connection refused")     # mirrors the live HTTPS failure
        return {"number": 3, "people": [{"name": "X", "craft": "ISS"}]}

    snap = HumansInSpaceClient(fetcher=fetch).fetch()
    assert snap.total == 3
    assert seen[0].startswith("https://") and seen[1].startswith("http://")


def test_none_when_all_fetches_raise_and_no_fallback():
    def boom(url):
        raise OSError("down")
    assert HumansInSpaceClient(fetcher=boom).fetch() is None


def test_none_on_empty_or_garbage_payload():
    assert HumansInSpaceClient(fetcher=lambda u: {}).fetch() is None
    assert HumansInSpaceClient(fetcher=lambda u: {"people": []}).fetch() is None
    assert HumansInSpaceClient(fetcher=lambda u: {"number": 5}).fetch() is None
