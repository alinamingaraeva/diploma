class LLMError(Exception):
    """Базовое исключение для ошибок LLM"""
    pass

class LLMRateLimitError(LLMError):
    pass

class LLMTimeoutError(LLMError):
    pass

class LLMAuthError(LLMError):
    pass

class LLMProviderError(LLMError):
    pass