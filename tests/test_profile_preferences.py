"""Profile settings v1: helpers, storage, prompts, menus, onboarding."""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from handlers import profile as profile_handlers
from handlers.profile import home_keyboard, start_profile_onboarding
from services.storage import get_storage, init_storage, reset_storage_for_tests
from utils.i18n import t
from utils.profile_name_confirm import (
    CB_PROFILE_NAME_CHANGE,
    CB_PROFILE_NAME_OK,
    format_profile_name_confirm_prompt,
    profile_name_confirm_keyboard,
)
from utils.profile_preferences import (
    ADDRESS_FORMAL,
    ADDRESS_INFORMAL,
    LENGTH_BALANCED,
    LENGTH_DETAILED,
    LENGTH_EXPANDED,
    LENGTH_SHORT,
    PREF_FIELD_ADDRESS,
    PREF_FIELD_GENDER,
    PREF_FIELD_LENGTH,
    PREF_FIELD_NAME,
    PREF_FIELD_TONE,
    PROFILE_MENU_CALLBACKS,
    TONE_ELEGANT,
    TONE_INSPIRING,
    TONE_IRONIC,
    TONE_NEUTRAL,
    TONE_PLAYFUL,
    TONE_TENDER,
    TONE_WARM,
    ProfilePreferences,
    default_profile_preferences,
    is_profile_callback,
    merge_profile_preference,
    normalize_profile_preferences,
    profile_preferences_prompt_suffix,
    validate_display_name,
)
from utils.profile_ui import profile_main_keyboard, profile_main_text
from utils.prompts import IMAGE_STYLE_CALLBACKS, TEXT_STYLE_CALLBACKS, build_text_system_prompt


def test_default_profile_preferences() -> None:
    prefs = default_profile_preferences()
    assert prefs.address_style == ADDRESS_INFORMAL
    assert prefs.text_tone == TONE_WARM
    assert prefs.text_length == LENGTH_BALANCED
    assert prefs.gender_or_wording == ""
    assert prefs.display_name == ""


def test_legacy_gender_stripped_on_normalize() -> None:
    prefs = normalize_profile_preferences({PREF_FIELD_GENDER: "feminine"})
    assert prefs.gender_or_wording == ""
    prefs2 = normalize_profile_preferences({PREF_FIELD_GENDER: "male"})
    assert prefs2.gender_or_wording == ""
    prefs3 = normalize_profile_preferences({PREF_FIELD_GENDER: "neutral"})
    assert prefs3.gender_or_wording == ""


def test_normalize_ignores_invalid_values() -> None:
    prefs = normalize_profile_preferences(
        {
            PREF_FIELD_ADDRESS: "invalid",
            PREF_FIELD_TONE: TONE_NEUTRAL,
            PREF_FIELD_LENGTH: "???",
            PREF_FIELD_GENDER: "other",
        }
    )
    assert prefs.address_style == ADDRESS_INFORMAL
    assert prefs.text_tone == TONE_NEUTRAL
    assert prefs.text_length == LENGTH_BALANCED
    assert prefs.gender_or_wording == ""


def test_normalize_new_tone_and_length_values() -> None:
    prefs = normalize_profile_preferences(
        {
            PREF_FIELD_TONE: TONE_TENDER,
            PREF_FIELD_LENGTH: LENGTH_EXPANDED,
        }
    )
    assert prefs.text_tone == TONE_TENDER
    assert prefs.text_length == LENGTH_EXPANDED


def test_merge_updates_one_field_without_losing_others() -> None:
    base = merge_profile_preference(
        default_profile_preferences(),
        display_name="Anna",
        text_tone=TONE_ELEGANT,
    )
    merged = merge_profile_preference(base, address_style=ADDRESS_FORMAL)
    assert merged.display_name == "Anna"
    assert merged.address_style == ADDRESS_FORMAL
    assert merged.text_tone == TONE_ELEGANT
    ignored = merge_profile_preference(merged, text_tone="not_a_tone")
    assert ignored.text_tone == TONE_ELEGANT


def test_validate_display_name() -> None:
    assert validate_display_name("Маша") == "Маша"
    assert validate_display_name("") is None
    assert validate_display_name("x" * 41) is None
    assert validate_display_name("line\nbreak") is None


def test_storage_malformed_and_partial_json(tmp_path: Path) -> None:
    reset_storage_for_tests()
    init_storage(tmp_path / "bad_json.db")
    st = get_storage()
    uid = 42
    st.set_user_lang(uid, "en")
    with st._conn() as conn:
        conn.execute(
            "UPDATE user_prefs SET profile_preferences_json = ? WHERE user_id = ?",
            ("not-json{", uid),
        )
    assert st.get_profile_preferences(uid) == default_profile_preferences()
    with st._conn() as conn:
        conn.execute(
            "UPDATE user_prefs SET profile_preferences_json = ? WHERE user_id = ?",
            ('{"text_tone": "playful", "display_name": "Kate"}', uid),
        )
    partial = st.get_profile_preferences(uid)
    assert partial.text_tone == TONE_PLAYFUL
    assert partial.display_name == "Kate"
    assert partial.address_style == ADDRESS_INFORMAL
    reset_storage_for_tests()


def test_storage_migration_duplicate_column_safe(tmp_path: Path) -> None:
    reset_storage_for_tests()
    db = tmp_path / "legacy.db"
    import sqlite3

    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE user_prefs (user_id INTEGER PRIMARY KEY, lang TEXT NOT NULL DEFAULT 'ru')"
    )
    conn.execute("INSERT INTO user_prefs (user_id, lang) VALUES (1, 'en')")
    conn.commit()
    conn.close()
    init_storage(db)
    st = get_storage()
    prefs = st.get_profile_preferences(1)
    assert prefs == default_profile_preferences()
    st.update_profile_preference(1, display_name="Legacy")
    assert st.get_profile_preferences(1).display_name == "Legacy"
    assert st.get_user_lang(1) == "en"
    reset_storage_for_tests()


def test_storage_roundtrip_and_partial_update(tmp_path: Path) -> None:
    reset_storage_for_tests()
    init_storage(tmp_path / "prefs.db")
    st = get_storage()
    uid = 9001
    assert st.get_profile_preferences(uid) == default_profile_preferences()
    st.update_profile_preference(uid, text_tone=TONE_PLAYFUL, display_name="Sam")
    loaded = st.get_profile_preferences(uid)
    assert loaded.text_tone == TONE_PLAYFUL
    assert loaded.display_name == "Sam"
    st.update_profile_preference(
        uid,
        text_length=LENGTH_DETAILED,
        address_style=ADDRESS_FORMAL,
    )
    loaded2 = st.get_profile_preferences(uid)
    assert loaded2.display_name == "Sam"
    assert loaded2.text_tone == TONE_PLAYFUL
    assert loaded2.address_style == ADDRESS_FORMAL
    assert loaded2.gender_or_wording == ""
    reset_storage_for_tests()


def test_storage_legacy_gender_json_not_breaking(tmp_path: Path) -> None:
    reset_storage_for_tests()
    init_storage(tmp_path / "legacy_gender.db")
    st = get_storage()
    uid = 7
    with st._conn() as conn:
        conn.execute(
            "INSERT INTO user_prefs (user_id, lang, profile_preferences_json) VALUES (?, 'ru', ?)",
            (uid, '{"display_name": "Ira", "gender_or_wording": "female"}'),
        )
    prefs = st.get_profile_preferences(uid)
    assert prefs.display_name == "Ira"
    assert prefs.gender_or_wording == ""
    reset_storage_for_tests()


def test_user_needs_onboarding_only_name(tmp_path: Path) -> None:
    reset_storage_for_tests()
    init_storage(tmp_path / "onboard.db")
    st = get_storage()
    assert st.user_needs_profile_onboarding(1) is True
    st.update_profile_preference(1, display_name="Alex")
    assert st.user_needs_profile_onboarding(1) is False
    reset_storage_for_tests()


def test_prompt_includes_profile_preferences_without_gender() -> None:
    prefs = ProfilePreferences(
        display_name="Maria",
        gender_or_wording="female",
        address_style=ADDRESS_FORMAL,
        text_tone=TONE_NEUTRAL,
        text_length=LENGTH_SHORT,
    )
    s_ru = build_text_system_prompt("occasion_loved", "text_warm", "ru", profile_prefs=prefs)
    assert "Maria" in s_ru
    assert "на вы" in s_ru or "вы" in s_ru
    assert "нейтраль" in s_ru
    assert "женск" not in s_ru.lower()
    assert "мужск" not in s_ru.lower()
    assert "противоречат" in s_ru
    s_en = build_text_system_prompt("occasion_loved", "text_warm", "en", profile_prefs=prefs)
    assert "Maria" in s_en
    assert "feminine" not in s_en.lower()
    assert "masculine" not in s_en.lower()
    assert "consistent with audience" in s_en.lower()


def test_prompt_suffix_new_tones() -> None:
    prefs = merge_profile_preference(
        default_profile_preferences(),
        text_tone=TONE_INSPIRING,
        text_length=LENGTH_EXPANDED,
    )
    suffix = profile_preferences_prompt_suffix(prefs, "ru")
    assert "вдохнов" in suffix
    assert "развёрнут" in suffix
    assert "женск" not in suffix.lower()


def test_ironic_tone_valid_and_prompt_is_gentle() -> None:
    prefs = merge_profile_preference(default_profile_preferences(), text_tone=TONE_IRONIC)
    assert prefs.text_tone == TONE_IRONIC
    suffix_ru = profile_preferences_prompt_suffix(prefs, "ru")
    assert "ирон" in suffix_ru
    assert "насмеш" in suffix_ru
    assert "колк" in suffix_ru
    suffix_en = profile_preferences_prompt_suffix(prefs, "en")
    assert "ironic" in suffix_en.lower()
    assert "sarcasm" in suffix_en.lower()
    assert "mockery" in suffix_en.lower()


def test_home_keyboard_layout() -> None:
    kb = home_keyboard("ru")
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    labels = [btn.text for row in kb.inline_keyboard for btn in row]
    assert "change_lang" not in callbacks
    assert "profile:main" in callbacks
    assert "action_create_card" in callbacks
    assert "action_help" in callbacks
    assert any("Профиль" in text for text in labels)


def test_profile_main_keyboard_no_gender() -> None:
    kb = profile_main_keyboard("en")
    callbacks = {btn.callback_data for row in kb.inline_keyboard for btn in row}
    assert "profile:name" in callbacks
    assert "profile:lang" in callbacks
    assert "profile:address" in callbacks
    assert "profile:gender" not in callbacks
    assert not any(cb.startswith("profile:set:") for cb in callbacks)


def test_profile_callbacks_namespaced() -> None:
    wizard_callbacks = (
        TEXT_STYLE_CALLBACKS
        | IMAGE_STYLE_CALLBACKS
        | {
            "occasion_clients",
            "action_create_card",
            "action_help",
            "change_lang",
            "lang_ru",
            "lang_en",
        }
    )
    assert PROFILE_MENU_CALLBACKS.isdisjoint(wizard_callbacks)
    assert is_profile_callback("profile:set:tone:warm")
    assert not is_profile_callback("action_help")


def test_english_address_labels_casual_polite() -> None:
    assert t("pref_address_informal", "en") == "casual"
    assert t("pref_address_formal", "en") == "polite"
    assert t("pref_address_informal", "ru") == "на ты"


def test_profile_main_summary_text_no_gender() -> None:
    prefs = merge_profile_preference(
        default_profile_preferences(),
        display_name="Ира",
        address_style=ADDRESS_FORMAL,
        text_tone=TONE_NEUTRAL,
        text_length=LENGTH_SHORT,
    )
    text = profile_main_text(prefs, "ru", ui_lang="ru")
    assert "Ира" in text
    assert "на вы" in text
    assert "нейтральный" in text
    assert "тексты открыток" in text
    assert "Пол" not in text
    assert "Gender" not in text


def test_onboarding_first_message_copy() -> None:
    """First-start onboarding uses the warm intro, not the old short greeting."""
    ru = t("onboarding_ask_name", "ru")
    en = t("onboarding_ask_name", "en")
    assert "пол" not in ru.lower()
    assert "gender" not in en.lower()
    assert "помогу собрать открытку" in ru
    assert "картинку и текст" in ru
    assert "как мне к вам обращаться" in ru.lower()
    assert "познакомимся" in ru.lower()
    assert "Как к вам обращаться?" not in ru
    assert "help you create a card" in en
    assert "image and text" in en
    assert "what should i call you" in en.lower()
    assert "get acquainted" in en.lower()
    assert "What should we call you?" not in en


def test_onboarding_handler_uses_onboarding_ask_name_key() -> None:
    source = inspect.getsource(start_profile_onboarding)
    assert 't("onboarding_ask_name"' in source
    assert 't("profile_ask_name"' not in source


def test_onboarding_start_sets_name_state_only() -> None:
    source = inspect.getsource(start_profile_onboarding)
    assert "onboarding_name" in source
    assert "onboarding_gender" not in source
    assert "onboarding_ask_gender" not in source


def test_name_not_saved_before_confirm() -> None:
    for fn_name in ("on_onboarding_name_text", "on_editing_name_text"):
        source = inspect.getsource(getattr(profile_handlers, fn_name))
        assert "update_profile_preference" not in source
    confirm_source = inspect.getsource(profile_handlers.on_profile_name_confirm_action)
    assert "update_profile_preference" in confirm_source
    assert "PROFILE_NAME_CONFIRM_CALLBACKS" in confirm_source


def test_name_confirm_keyboard_labels() -> None:
    kb = profile_name_confirm_keyboard("ru")
    labels = [btn.text for row in kb.inline_keyboard for btn in row]
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "✅ Да" in labels
    assert "✏️ Изменить" in labels
    assert CB_PROFILE_NAME_OK in callbacks
    assert CB_PROFILE_NAME_CHANGE in callbacks


def test_name_confirm_prompt() -> None:
    text = format_profile_name_confirm_prompt("en", "Sam")
    assert "Sam" in text
    assert "correct" in text.lower()


def test_finish_onboarding_no_double_greeting() -> None:
    source = inspect.getsource(profile_handlers._finish_onboarding)
    assert "home_welcome" not in source
    assert "onboarding_done" in source


def test_start_returning_message() -> None:
    assert "{name}" in t("start_returning", "ru")
    assert "добро пожаловать" in t("start_returning", "ru").lower()
