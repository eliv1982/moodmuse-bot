"""Last-card persistence: the clean original travels with its context; legacy rows still load."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from services.storage import BotStorage, LastCardContext, get_storage


def _ctx(**overrides: object) -> LastCardContext:
    values: dict[str, object] = {
        "occasion": "occasion_loved",
        "image_description": "cake",
        "holiday": "birthday",
        "image_style": "style_realistic",
        "text_style": "text_warm",
        "lang": "ru",
        "image_prompt_en": "a cake",
        "photo_file_id": "file-1",
        "caption_html": "caption",
        "short_text": "Happy day",
    }
    values.update(overrides)
    return LastCardContext(**values)  # type: ignore[arg-type]


def test_original_is_stored_and_read_back_with_its_context() -> None:
    st = get_storage()
    st.save_last_card(1, _ctx(), original=b"CLEAN-1")

    ctx, original = st.get_last_card_with_original(1)

    assert original == b"CLEAN-1"
    assert ctx is not None
    assert (ctx.short_text, ctx.caption_html, ctx.photo_file_id) == ("Happy day", "caption", "file-1")


def test_plain_get_last_card_still_returns_only_the_context() -> None:
    st = get_storage()
    st.save_last_card(1, _ctx(), original=b"CLEAN-1")
    ctx = st.get_last_card(1)
    assert isinstance(ctx, LastCardContext)
    assert ctx.short_text == "Happy day"


def test_text_only_save_keeps_the_stored_original() -> None:
    st = get_storage()
    st.save_last_card(1, _ctx(), original=b"CLEAN-1")

    st.save_last_card(1, _ctx(short_text="New phrase", caption_html="new caption"))

    ctx, original = st.get_last_card_with_original(1)
    assert original == b"CLEAN-1"
    assert (ctx.short_text, ctx.caption_html) == ("New phrase", "new caption")  # type: ignore[union-attr]


def test_saving_a_new_image_replaces_context_and_original_together() -> None:
    st = get_storage()
    st.save_last_card(1, _ctx(short_text="first"), original=b"CLEAN-1")

    st.save_last_card(1, _ctx(short_text="second", photo_file_id="file-2"), original=b"CLEAN-2")

    ctx, original = st.get_last_card_with_original(1)
    assert original == b"CLEAN-2"
    assert (ctx.short_text, ctx.photo_file_id) == ("second", "file-2")  # type: ignore[union-attr]


def test_only_the_latest_card_per_user_is_kept() -> None:
    st = get_storage()
    st.save_last_card(1, _ctx(short_text="a"), original=b"A")
    st.save_last_card(1, _ctx(short_text="b"), original=b"B")
    st.save_last_card(2, _ctx(short_text="other"), original=b"OTHER")

    with closing(sqlite3.connect(st._db_path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM last_card WHERE user_id = 1").fetchone()[0] == 1
    assert st.get_last_card_with_original(1)[1] == b"B"
    assert st.get_last_card_with_original(2)[1] == b"OTHER"


def test_binary_original_round_trips_exactly() -> None:
    blob = bytes(range(256)) * 512
    st = get_storage()
    st.save_last_card(1, _ctx(), original=blob)
    assert st.get_last_card_with_original(1)[1] == blob


def test_unknown_user_has_no_card_and_no_original() -> None:
    assert get_storage().get_last_card_with_original(404) == (None, None)
    assert get_storage().get_last_card(404) is None


def test_corrupt_payload_reads_as_no_card() -> None:
    st = get_storage()
    with closing(sqlite3.connect(st._db_path)) as conn:
        conn.execute("INSERT INTO last_card (user_id, payload, original_image) VALUES (7, 'not json', x'00ff')")
        conn.commit()
    assert st.get_last_card_with_original(7) == (None, None)


# ----- legacy rows (saved before embedded captions) -----


def test_context_saved_without_short_text_loads_with_an_empty_one() -> None:
    legacy = {
        "occasion": "occasion_loved",
        "image_description": "cake",
        "holiday": "birthday",
        "image_style": "style_realistic",
        "text_style": "text_warm",
        "lang": "en",
        "image_prompt_en": "a cake",
        "photo_file_id": "legacy-file",
        "caption_html": "old caption",
    }
    ctx = LastCardContext.from_dict(legacy)
    assert ctx is not None
    assert ctx.short_text == ""
    assert ctx.photo_file_id == "legacy-file"


def test_legacy_row_without_original_loads_with_none() -> None:
    st = get_storage()
    st.save_last_card(1, _ctx(short_text=""))  # context only, like a card saved before this feature
    ctx, original = st.get_last_card_with_original(1)
    assert ctx is not None and original is None


def test_database_created_before_the_feature_is_migrated_in_place(tmp_path: Path) -> None:
    db = tmp_path / "old.db"
    legacy_payload = json.dumps(
        {
            "occasion": "occasion_loved",
            "image_description": "cake",
            "holiday": "birthday",
            "image_style": "style_realistic",
            "text_style": "text_warm",
            "lang": "ru",
            "image_prompt_en": "a cake",
            "photo_file_id": "legacy-file",
            "caption_html": "старая подпись",
        },
        ensure_ascii=False,
    )
    with closing(sqlite3.connect(db)) as conn:
        conn.execute("CREATE TABLE last_card (user_id INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
        conn.execute("INSERT INTO last_card VALUES (5, ?)", (legacy_payload,))
        conn.commit()

    st = BotStorage(db)
    ctx, original = st.get_last_card_with_original(5)

    assert original is None
    assert ctx is not None and ctx.caption_html == "старая подпись" and ctx.photo_file_id == "legacy-file"
    # The migrated table accepts an original, and opening it again is harmless.
    st.save_last_card(5, ctx, original=b"NEW-CLEAN")
    assert BotStorage(db).get_last_card_with_original(5)[1] == b"NEW-CLEAN"
