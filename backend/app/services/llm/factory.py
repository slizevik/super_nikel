from app.core.config import Settings
from app.services.llm.base import LLMConfigurationError, LLMProvider
from app.services.llm.budget import TokenBudget
from app.services.llm.yandex import YandexGPTProvider


def create_llm_provider(settings: Settings, token_budget: TokenBudget) -> LLMProvider:
    provider_name = settings.llm_provider.strip().lower()
    if provider_name != "yandex":
        raise LLMConfigurationError(
            f"Unsupported LLM_PROVIDER '{settings.llm_provider}'. "
            "Configure LLM_PROVIDER=yandex."
        )
    if not settings.yandex_cloud_api_key:
        raise LLMConfigurationError(
            "YANDEX_CLOUD_API_KEY is missing. Add Yandex Cloud API credentials "
            "to the local .env file to enable image analysis and entity extraction."
        )
    if not settings.yandex_cloud_folder:
        raise LLMConfigurationError(
            "YANDEX_CLOUD_FOLDER is missing. Add the Yandex Cloud folder ID "
            "to the local .env file."
        )
    return YandexGPTProvider(settings, token_budget)
