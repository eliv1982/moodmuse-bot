"""SQLite storage and limits."""
from pathlib import Path

from services.storage import LastCardContext, get_storage, init_storage, reset_storage_for_tests


def test_daily_limit_and_last_card(tmp_path: Path) -> None:
    reset_storage_for_tests()
    db = tmp_path / "t.db"
    init_storage(db)
    st = get_storage()
    uid = 4242
    assert st.get_daily_count(uid) == 0
    st.increment_generation(uid)
    assert st.get_daily_count(uid) == 1
    ctx = LastCardContext(
        occasion="occasion_clients",
        image_description="x",
        holiday="NY",
        image_style="style_realistic",
        text_style="text_warm",
        lang="ru",
        image_prompt_en="draft",
        photo_file_id="fid",
        caption_html="Hi",
    )
    st.save_last_card(uid, ctx)
    loaded = st.get_last_card(uid)
    assert loaded is not None
    assert loaded.image_prompt_en == "draft"
    assert loaded.photo_file_id == "fid"
    st.set_small_talk_enabled(False)
    assert st.is_small_talk_enabled() is False
    st.set_small_talk_enabled(True)
    assert st.is_small_talk_enabled() is True
    st.set_maintenance_message("down")
    assert st.get_maintenance_message() == "down"
    reset_storage_for_tests()
