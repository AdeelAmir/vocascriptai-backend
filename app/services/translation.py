import deepl
from app.services.settings_service import get_setting


async def get_deepl_keys() -> list[str]:
    key = await get_setting("DEEPL_API_KEY")
    return [key] if key else []


def _translate_with_keys(text: str, language_code: str, keys: list[str]) -> str:
    """Try translation with multiple keys as fallback."""
    if not text or language_code in {"en", "auto"}:
        return text

    last_error = None
    for key in keys:
        try:
            translator = deepl.Translator(key)
            result = translator.translate_text(text, target_lang=language_code.upper())
            return result.text
        except deepl.QuotaExceededException:
            last_error = "quota"
            continue
        except deepl.AuthorizationException:
            last_error = "auth"
            continue
        except Exception as e:
            last_error = str(e)
            continue

    raise Exception(f"All DeepL API keys failed. Last error: {last_error}")


def translate_text(text: str, language_code: str, keys: list[str]) -> str:
    if language_code in {"en", "auto"} or not text:
        return text
    if not keys:
        raise Exception("No DeepL API keys configured. Add DEEPL_API_KEY_1 in Settings.")
    return _translate_with_keys(text, language_code, keys)


def translate_list(items: list, language_code: str, keys: list[str]) -> list:
    """Translate a list of action items (dicts with title, description, prompt)."""
    if language_code in {"en", "auto"} or not items:
        return items

    translated = []
    for item in items:
        if isinstance(item, dict):
            translated_item = item.copy()
            for field in ["title", "description", "prompt"]:
                if item.get(field):
                    translated_item[field] = translate_text(str(item[field]), language_code, keys)
            translated.append(translated_item)
        else:
            translated.append(translate_text(str(item), language_code, keys))

    return translated


def translate_transcript(transcript: list[dict], language_code: str, keys: list[str]) -> list[dict]:
    if language_code in {"en", "auto"} or not transcript:
        return transcript
    
    translated = []
    for seg in transcript:
        t = seg.copy()
        if seg.get("text"):
            t["text"] = translate_text(seg["text"], language_code, keys)
        translated.append(t)
    return translated
