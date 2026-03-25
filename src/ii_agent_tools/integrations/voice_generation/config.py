from pydantic import BaseModel

LANGUAGE_ALIASES: dict[str, str] = {
    "en": "english",
    "english": "english",
    "vi": "vietnamese",
    "vn": "vietnamese",
    "vietnamese": "vietnamese",
    "hi": "hindi",
    "hindi": "hindi",
    "ja": "japanese",
    "jp": "japanese",
    "jpn": "japanese",
    "japanese": "japanese",
    "ko": "korean",
    "kr": "korean",
    "korea": "korean",
    "korean": "korean",
}


def normalize_language(language: str | None) -> str | None:
    if not language:
        return None
    normalized = language.strip().lower()
    if not normalized:
        return None
    primary = normalized.split("-", 1)[0].split("_", 1)[0]
    return LANGUAGE_ALIASES.get(primary) or LANGUAGE_ALIASES.get(normalized)


class VoiceGenerateConfig(BaseModel):
    elevenlabs_api_key: str | None = None
    elevenlabs_base_url: str = "https://api.elevenlabs.io"
    elevenlabs_default_voice_id: str | None = None
    elevenlabs_model: str | None = None
    elevenlabs_voice_id_english: str | None = None
    elevenlabs_voice_id_vietnamese: str | None = None
    elevenlabs_voice_id_hindi: str | None = None
    elevenlabs_voice_id_japanese: str | None = None
    elevenlabs_voice_id_korea: str | None = None
    google_ai_studio_api_key: str | None = None
    gcp_location: str | None = None
    gemini_model_name: str = "gemini-2.5-pro-preview-tts"
    gemini_default_voice_name: str = "Kore"
    gemini_voice_name_english: str | None = None
    gemini_voice_name_vietnamese: str | None = None
    gemini_voice_name_hindi: str | None = None
    gemini_voice_name_japanese: str | None = None
    gemini_voice_name_korean: str | None = None
    gcp_project_id: str | None = None
    gcs_output_bucket: str | None = None
    fal_api_key: str | None = None
    fal_model_name: str | None = None
    fal_request_mode: str = "async"

    def get_elevenlabs_voice_id_map(self) -> dict[str, str]:
        mapping = {
            "english": self.elevenlabs_voice_id_english,
            "vietnamese": self.elevenlabs_voice_id_vietnamese,
            "hindi": self.elevenlabs_voice_id_hindi,
            "japanese": self.elevenlabs_voice_id_japanese,
            "korean": self.elevenlabs_voice_id_korea,
        }
        return {key: value for key, value in mapping.items() if value}

    def get_elevenlabs_voice_id_for_language(self, language: str | None) -> str | None:
        key = normalize_language(language)
        if not key:
            return None
        return self.get_elevenlabs_voice_id_map().get(key)

    def get_gemini_voice_name_map(self) -> dict[str, str]:
        mapping = {
            "english": self.gemini_voice_name_english,
            "vietnamese": self.gemini_voice_name_vietnamese,
            "hindi": self.gemini_voice_name_hindi,
            "japanese": self.gemini_voice_name_japanese,
            "korean": self.gemini_voice_name_korean,
        }
        return {key: value for key, value in mapping.items() if value}

    def get_gemini_voice_name_for_language(self, language: str | None) -> str | None:
        key = normalize_language(language)
        if not key:
            return None
        return self.get_gemini_voice_name_map().get(key)

    def has_gemini_tts_credentials(self) -> bool:
        return bool(self.google_ai_studio_api_key) or bool(
            self.gcp_project_id and self.gcp_location
        )
