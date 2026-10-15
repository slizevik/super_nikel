from app.core.config import Settings
from app.services.llm.base import LLMConfigurationError, LLMProvider
from app.services.llm.budget import TokenBudget
from app.services.llm.gigachat import GigaChatProvider
from app.services.llm.yandex import YandexGPTProvider


def create_llm_provider(settings: Settings, token_budget: TokenBudget) -> LLMProvider:
    provider_name = settings.llm_provider.strip().lower()
    if provider_name == "gigachat":
        if not settings.gigachat_credentials:
            raise LLMConfigurationError(
                "GIGACHAT_CREDENTIALS is missing. Add the GigaChat Authorization "
                "Key to the local .env file."
            )
        return GigaChatProvider(settings, token_budget)
    if provider_name == "yandex":
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
    raise LLMConfigurationError(
        f"Unsupported LLM_PROVIDER '{settings.llm_provider}'. "
        "Configure LLM_PROVIDER=yandex or LLM_PROVIDER=gigachat."
    )
