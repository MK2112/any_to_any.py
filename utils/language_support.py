import locale

from utils.languages import LANGUAGE_CODES as CODES
from utils.languages import MANDARIN_SIMPLIFIED, JAPANESE, FRENCH, SPANISH, ITALIAN, GERMAN, PORTUGUESE, RUSSIAN, KOREAN, ENGLISH
from utils.languages import POLISH, HINDI, UKRAINIAN, ARABIC, INDONESIAN, TURKISH, VIETNAMESE, THAI, DUTCH, SWEDISH, DANISH
from utils.languages import FINNISH, NORWEGIAN, ICELANDIC, HEBREW, CZECH, ROMANIAN, MALAY, BULGARIAN, HUNGARIAN, GREEK, SLOVAK
from utils.languages import MANDARIN_TRADITIONAL, FARSI, BENGALI, URDU, SWAHILI, PUNJABI_INDIAN, PUNJABI_PAKISTAN, TAGALOG
from utils.languages import BURMESE, TAMIL, TELUGU, MARATHI, CANTONESE

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
}


def get_system_language():
    lang_code = locale.getlocale()[0] or "en_US"
    # Try mapping to any of the supported languages
    for code, lang in LANGUAGE_CODES.items():
        if lang_code in code:
            return lang
    # Fallback to English
    return "English"


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
