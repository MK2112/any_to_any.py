import utils.language_support as lang

# Language support logic tests
# Mainly related to get_system_language and get_translation funcs

def test_get_system_language_handles_none_locale(monkeypatch):
    monkeypatch.setattr(lang.locale, "getlocale", lambda: (None, None))
    assert lang.get_system_language() == "English"


def test_get_system_language_handles_partial_code_match(monkeypatch):
    monkeypatch.setattr(lang.locale, "getlocale", lambda: ("en", "UTF-8"))
    assert lang.get_system_language() == "English"


def test_get_system_language_returns_fallback_for_unknown_code(monkeypatch):
    monkeypatch.setattr(lang.locale, "getlocale", lambda: ("zz_ZZ", "UTF-8"))
    assert lang.get_system_language() == "English"


def test_get_system_language_maps_mx_spanish(monkeypatch):
    monkeypatch.setattr(lang.locale, "getlocale", lambda: ("es_MX", "UTF-8"))
    assert lang.get_system_language() == "Spanish"


def test_get_system_language_maps_exact_locale(monkeypatch):
    monkeypatch.setattr(lang.locale, "getlocale", lambda: ("de_DE", "UTF-8"))
    assert lang.get_system_language() == "German"


def test_get_translation_uses_explicit_language():
    value = lang.get_translation("convert", "French")
    assert value
    assert isinstance(value, str)


def test_get_translation_missing_key_returns_key():
    key = "__this_key_should_not_exist__"
    assert lang.get_translation(key, "English") == key


def test_get_translation_unknown_language_falls_back_to_english():
    assert lang.get_translation("convert", "Klingon") == lang.TRANSLATIONS["English"]["convert"]


def test_get_translation_without_language_uses_system_language(monkeypatch):
    monkeypatch.setattr(lang, "get_system_language", lambda: "German")
    assert lang.get_translation("convert") == lang.TRANSLATIONS["German"]["convert"]


def test_get_all_translations_with_known_language():
    values = lang.get_all_translations("Japanese")
    assert isinstance(values, dict)
    assert "convert" in values


def test_get_all_translations_fallback_to_english_for_unknown_language():
    assert lang.get_all_translations("Unknown") is lang.TRANSLATIONS["English"]


def test_get_all_translations_without_language_uses_system_language(monkeypatch):
    monkeypatch.setattr(lang, "get_system_language", lambda: "Italian")
    assert lang.get_all_translations() is lang.TRANSLATIONS["Italian"]
