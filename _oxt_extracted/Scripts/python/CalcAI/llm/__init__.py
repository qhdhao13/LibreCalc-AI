from .base_provider import BaseLLMProvider

# LLM providers require third-party libs (httpx, requests, etc.)
# which may not be available in LO's embedded Python.
# Import them lazily so llm.tool_definitions can be used standalone.
try:
    from .openrouter_provider import OpenRouterProvider
except ImportError:
    OpenRouterProvider = None

try:
    from .ollama_provider import OllamaProvider
except ImportError:
    OllamaProvider = None

try:
    from .gemini_provider import GeminiProvider
except ImportError:
    GeminiProvider = None

try:
    from .groq_provider import GroqProvider
except ImportError:
    GroqProvider = None

try:
    from .hunyuan_provider import HunyuanProvider
except ImportError:
    HunyuanProvider = None

__all__ = [
    "BaseLLMProvider",
    "OpenRouterProvider",
    "OllamaProvider",
    "GeminiProvider",
    "GroqProvider",
    "HunyuanProvider",
]
