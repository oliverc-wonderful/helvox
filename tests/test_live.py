import json

import pytest

from helvox.utils.live import save_review


def test_review_is_separate_and_older_delivery_cannot_revert_it(tmp_path):
    take = tmp_path / "take.json"
    take.write_text('{"text_ch":"Frozen transcript"}')
    newest = {
        "recording_id": "take",
        "status": "re_record",
        "note": "Wrong ending",
        "reviewed_ts": 20,
    }
    assert save_review(tmp_path, newest)
    assert not save_review(
        tmp_path, {**newest, "status": "approved", "reviewed_ts": 10}
    )
    assert json.loads((tmp_path / "review.json").read_text()) == newest
    assert take.read_text() == '{"text_ch":"Frozen transcript"}'


def test_invalid_review_cannot_be_persisted(tmp_path):
    with pytest.raises(ValueError):
        save_review(tmp_path, {"status": "unknown", "reviewed_ts": 1})
    with pytest.raises(ValueError):
        save_review(tmp_path, {"status": "approved", "reviewed_ts": -1})
    assert not (tmp_path / "review.json").exists()
