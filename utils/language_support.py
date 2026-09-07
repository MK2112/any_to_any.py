import os
import locale
import warnings

from utils.languages import LANGUAGE_CODES as CODES
from utils.languages import MANDARIN_SIMPLIFIED, JAPANESE, FRENCH, SPANISH, ITALIAN, GERMAN, PORTUGUESE, RUSSIAN, KOREAN, ENGLISH
from utils.languages import POLISH, HINDI, UKRAINIAN, ARABIC, INDONESIAN, TURKISH, VIETNAMESE, THAI, DUTCH, SWEDISH, DANISH
from utils.languages import FINNISH, NORWEGIAN, ICELANDIC, HEBREW, CZECH, ROMANIAN, MALAY, BULGARIAN, HUNGARIAN, GREEK, SLOVAK
from utils.languages import MANDARIN_TRADITIONAL, FARSI, BENGALI, URDU, SWAHILI, PUNJABI_INDIAN, PUNJABI_PAKISTAN, TAGALOG
from utils.languages import BURMESE, TAMIL, TELUGU, MARATHI, CANTONESE, CATALAN, CROATIAN, SERBIAN, BOSNIAN

LANGUAGE_CODES = CODES

TRANSLATIONS = {
    "Mandarin (Simplified)": MANDARIN_SIMPLIFIED,
    "Japanese": JAPANESE,
    "French": FRENCH,
    "Spanish": SPANISH,
    "Mexican Spanish": SPANISH,
    "Italian": ITALIAN,
    "German": GERMAN,
    "Portuguese (Brazil)": PORTUGUESE,
    "Portuguese (Portugal)": PORTUGUESE,
    "Russian": RUSSIAN,
    "Korean": KOREAN,
    "English": ENGLISH,
    "Polish": POLISH,
    "Hindi": HINDI,
    "Ukrainian": UKRAINIAN,
    "Arabic": ARABIC,
    "Indonesian": INDONESIAN,
    "Turkish": TURKISH,
    "Vietnamese": VIETNAMESE,
    "Thai": THAI,
    "Dutch": DUTCH,
    "Swedish": SWEDISH,
    "Danish": DANISH,
    "Finnish": FINNISH,
    "Norwegian": NORWEGIAN,
    "Icelandic": ICELANDIC,
    "Hebrew": HEBREW,
    "Czech": CZECH,
    "Romanian": ROMANIAN,
    "Malay": MALAY,
    "Bulgarian": BULGARIAN,
    "Hungarian": HUNGARIAN,
    "Greek": GREEK,
    "Slovak": SLOVAK,
    "Mandarin (Traditional)": MANDARIN_TRADITIONAL,
    "Cantonese": CANTONESE,
    "Persian (Farsi)": FARSI,
    "Bengali": BENGALI,
    "Urdu": URDU,
    "Swahili": SWAHILI,
    "Punjabi (Indian)": PUNJABI_INDIAN,
    "Punjabi (Pakistan)": PUNJABI_PAKISTAN,
    "Tagalog": TAGALOG,
    "Burmese": BURMESE,
    "Tamil": TAMIL,
    "Telugu": TELUGU,
    "Marathi": MARATHI,
    "Catalan": CATALAN,
    "Croatian": CROATIAN,
    "Serbian": SERBIAN,
    "Bosnian": BOSNIAN,
}


def get_system_language():
    # Detect the OS language (Linux and Windows)
    candidates = []
    try:
        loc = locale.getlocale()[0]
        if loc:
            candidates.append(loc)
    except Exception:
        pass
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            try:
                dloc = locale.getdefaultlocale()[0]
            except Exception:
                dloc = None
            if dloc:
                candidates.append(dloc)
    except Exception:
        pass
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        try:
            val = os.environ.get(var)
        except Exception:
            continue
        if not val:
            continue
        for part in val.split(":"):
            part = part.strip().strip(";").strip()
            if part:
                candidates.append(part)

    for raw in candidates:
        resolved = _resolve_language_tag(raw)
        if resolved is not None:
            return resolved
        if _is_explicit_unsupported(raw):
            return "English"
    return "English"


def _is_explicit_unsupported(raw):
    try:
        if raw != locale.getlocale()[0]:
            return False
    except Exception:
        return False
    if not isinstance(raw, str):
        return False
    tag = raw.strip().split(".")[0].split("@")[0].strip().replace("-", "_")
    if not tag or tag.lower() in ("c", "posix", "c.utf8", "c.utf_8", "utf8", "utf_8"):
        return False
    return _resolve_language_tag(raw) is None

# English display names used by Windows locale strings
_WINDOWS_LANGUAGE_NAMES = {
    "chinese": "zh",
    "mandarin": "zh",
    "japanese": "ja",
    "french": "fr",
    "spanish": "es",
    "italian": "it",
    "german": "de",
    "portuguese": "pt",
    "russian": "ru",
    "korean": "ko",
    "english": "en",
    "polish": "pl",
    "ukrainian": "uk",
    "hindi": "hi",
    "arabic": "ar",
    "indonesian": "id",
    "turkish": "tr",
    "vietnamese": "vi",
    "thai": "th",
    "dutch": "nl",
    "flemish": "nl",
    "swedish": "sv",
    "danish": "da",
    "finnish": "fi",
    "norwegian": "no",
    "icelandic": "is",
    "hebrew": "he",
    "czech": "cs",
    "romanian": "ro",
    "malay": "ms",
    "bulgarian": "bg",
    "hungarian": "hu",
    "slovak": "sk",
    "greek": "el",
    "persian": "fa",
    "farsi": "fa",
    "bengali": "bn",
    "bangla": "bn",
    "urdu": "ur",
    "swahili": "sw",
    "kiswahili": "sw",
    "punjabi": "pa",
    "panjabi": "pa",
    "tagalog": "tl",
    "filipino": "tl",
    "burmese": "my",
    "myanmar": "my",
    "tamil": "ta",
    "telugu": "te",
    "marathi": "mr",
    "catalan": "ca",
    "valencian": "ca",
    "croatian": "hr",
    "croat": "hr",
    "serbian": "sr",
    "serb": "sr",
    "bosnian": "bs",
}

# Windows region display names mapped to ISO 3166 codes for languages
_WINDOWS_REGION_ALIASES = {
    "china": "CN",
    "taiwan": "TW",
    "hong kong": "HK",
    "hongkong": "HK",
    "macau": "HK",
    "macao": "HK",
    "singapore": "CN",
    "brazil": "BR",
    "brasil": "BR",
    "portugal": "PT",
    "mexico": "MX",
    "spain": "ES",
    "india": "IN",
    "pakistan": "PK",
    "kenya": "KE",
    "tanzania": "TZ",
    "serbia": "RS",
    "bosnia": "BA",
    "bosnia and herzegovina": "BA",
    "montenegro": "ME",
    "croatia": "HR",
    "catalonia": "ES",
}


def _resolve_language_tag(raw):
    # Normalize one locale tag to a language name, or None when unusable
    try:
        if not isinstance(raw, str):
            return None
        tag = raw.strip()
        if not tag:
            return None
        tag = tag.split(".")[0].split("@")[0].strip()
        if " " in tag and "_" not in tag:
            tag = tag.split()[0]
        if not tag or tag.lower() in (
            "c",
            "posix",
            "c.utf8",
            "c.utf_8",
            "utf8",
            "utf_8",
        ):
            return None
        tag = tag.replace("-", "_")
        lowered = tag.lower()
        for code, lang in LANGUAGE_CODES.items():
            if lowered == code.lower():
                return lang if lang in TRANSLATIONS else lang
        parts = tag.split("_")
        lang_raw = (parts[0] or "").strip()
        region_raw = (parts[1] or "").strip() if len(parts) > 1 else ""
        if not lang_raw:
            return None
        lang_key = lang_raw.split("(")[0].strip().split()[0].lower() if lang_raw else ""
        iso = _WINDOWS_LANGUAGE_NAMES.get(lang_key, lang_key)
        grouped = [
            (code, lang)
            for code, lang in LANGUAGE_CODES.items()
            if code.split("_")[0].lower() == iso
        ]
        if not grouped:
            return None
        if len(grouped) == 1 or not region_raw:
            return grouped[0][1]
        region_key = region_raw.split("(")[0].strip().lower()
        region_iso = _WINDOWS_REGION_ALIASES.get(region_key, region_key.upper())
        for code, lang in grouped:
            if code.split("_")[1].upper() == region_iso:
                return lang
        return grouped[0][1]
    except Exception:
        return None

resolve_language_tag = _resolve_language_tag


def get_translation(key, language=None):
    if language is None:
        language = get_system_language()
    # Fallback to English on missing translation
    return TRANSLATIONS.get(language, TRANSLATIONS["English"]).get(key, key)


def get_all_translations(language=None):
    if language is None:
        language = get_system_language()
    # Fallback to English if lang not supported
    return TRANSLATIONS.get(language, TRANSLATIONS["English"])
