import os
import re
import asyncio
from abc import ABC, abstractmethod
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    retry_if_exception,
)
import openai
from google import genai
from google.genai import types, errors as genai_errors
import groq
from groq import AsyncGroq
import anthropic


# ── Base Class ────────────────────────────────────────────────────────────────

class LLMProvider(ABC):

    @staticmethod
    def _strip_think_tags(content: str) -> str:
        if not content:
            return ""
        return re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()

    @abstractmethod
    def generate(self, prompt: str, system_prompt: str = "", max_tokens: int = 8192) -> str:
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        pass

    # Default async wrapper — works for all providers immediately.
    # NOTE: NVIDIA, Gemini, OpenAI use asyncio.to_thread.
    # True async clients for these providers are future debt.
    async def async_generate(self, prompt: str, system_prompt: str = "", max_tokens: int = 8192) -> str:
        return await asyncio.to_thread(self.generate, prompt, system_prompt, max_tokens)


# ── Groq ──────────────────────────────────────────────────────────────────────

class GroqProvider(LLMProvider):
    def __init__(self, api_key: str, model_name: str = "qwen/qwen3-32b"):
        self.client = groq.Groq(api_key=api_key)
        self.async_client = AsyncGroq(api_key=api_key)
        self.model_name = model_name
        self.total_tokens_used = 0

    def _build_messages(self, prompt: str, system_prompt: str) -> list:
        messages = []
        if system_prompt:
            messages.append({'role': 'system', 'content': system_prompt})
        messages.append({'role': 'user', 'content': prompt})
        return messages

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((groq.RateLimitError, groq.InternalServerError))
    )
    def generate(self, prompt: str, system_prompt: str = "", max_tokens: int = 8192) -> str:
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=self._build_messages(prompt, system_prompt),
            temperature=0,
            max_tokens=max_tokens
        )
        if response.usage:
            self.total_tokens_used += response.usage.total_tokens
            print(f"   📊 Tokens: {response.usage.prompt_tokens} in / "
                  f"{response.usage.completion_tokens} out "
                  f"(total: {response.usage.total_tokens} | session: {self.total_tokens_used})")

        return self._strip_think_tags(response.choices[0].message.content)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((groq.RateLimitError, groq.InternalServerError))
    )
    async def async_generate(self, prompt: str, system_prompt: str = "", max_tokens: int = 8192) -> str:
        response = await self.async_client.chat.completions.create(
            model=self.model_name,
            messages=self._build_messages(prompt, system_prompt),
            temperature=0,
            max_tokens=max_tokens
        )
        if response.usage:
            self.total_tokens_used += response.usage.total_tokens
            print(f"   📊 Tokens: {response.usage.prompt_tokens} in / "
                  f"{response.usage.completion_tokens} out "
                  f"(total: {response.usage.total_tokens} | session: {self.total_tokens_used})")

        return self._strip_think_tags(response.choices[0].message.content)

    def get_model_name(self) -> str:
        return self.model_name


# ── OpenAI ────────────────────────────────────────────────────────────────────
# NOTE: uses base class asyncio.to_thread async — true async client is future debt

class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model_name: str = "gpt-4o"):
        self.client = openai.OpenAI(api_key=api_key)
        self.model_name = model_name
        self.total_tokens_used = 0

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((openai.RateLimitError, openai.InternalServerError))
    )
    def generate(self, prompt: str, system_prompt: str = "", max_tokens: int = 8192) -> str:
        messages = []
        if system_prompt:
            messages.append({'role': 'system', 'content': system_prompt})
        messages.append({'role': 'user', 'content': prompt})

        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=0,
            max_tokens=max_tokens
        )
        if response.usage:
            self.total_tokens_used += response.usage.total_tokens
            print(f"   📊 Tokens: {response.usage.prompt_tokens} in / "
                  f"{response.usage.completion_tokens} out "
                  f"(total: {response.usage.total_tokens} | session: {self.total_tokens_used})")

        return self._strip_think_tags(response.choices[0].message.content)

    def get_model_name(self) -> str:
        return self.model_name


# ── Gemini ────────────────────────────────────────────────────────────────────
# NOTE: uses base class asyncio.to_thread async — true async client is future debt

def _is_retryable_gemini(exc: Exception) -> bool:
    """Retry on 5xx (ServerError) and 429 only (ClientError with code 429).
    All other 4xx (including 400 Bad Request) fail immediately — they will
    never succeed on retry and burning quota on them is wrong.
    """
    if isinstance(exc, genai_errors.ServerError):
        return True
    if isinstance(exc, genai_errors.ClientError):
        return getattr(exc, 'code', None) == 429
    return False


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash"):
        if not api_key:
            raise ValueError("Gemini API Key is missing. Set GEMINI_API_KEY in .env")
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name
        self.total_tokens_used = 0

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception(_is_retryable_gemini)
    )
    def generate(self, prompt: str, system_prompt: str = "", max_tokens: int = 8192) -> str:
        config = types.GenerateContentConfig(
            system_instruction=system_prompt if system_prompt else None,
            temperature=0
        )
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=config
        )
        if response.usage_metadata:
            input_tokens = response.usage_metadata.prompt_token_count or 0
            output_tokens = response.usage_metadata.candidates_token_count or 0
            self.total_tokens_used += input_tokens + output_tokens
            print(f"   📊 Tokens: {input_tokens} in / "
                  f"{output_tokens} out "
                  f"(total: {input_tokens + output_tokens} | session: {self.total_tokens_used})")
        return self._strip_think_tags(response.text)

    def get_model_name(self) -> str:
        return self.model_name


# ── NVIDIA NIM ────────────────────────────────────────────────────────────────
# NOTE: uses base class asyncio.to_thread async — true async client is future debt

class NvidiaProvider(LLMProvider):
    def __init__(self, api_key: str, model_name: str = "nvidia/llama-3.3-nemotron-super-49b-v1.5"):
        self.client = openai.OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=api_key
        )
        self.model_name = model_name
        self.total_tokens_used = 0

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((openai.RateLimitError, openai.InternalServerError))
    )
    def generate(self, prompt: str, system_prompt: str = "", max_tokens: int = 8192) -> str:
        messages = []
        if system_prompt:
            messages.append({'role': 'system', 'content': system_prompt})
        messages.append({'role': 'user', 'content': prompt})

        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=0,
            max_tokens=max_tokens
        )
        if response.usage:
            self.total_tokens_used += response.usage.total_tokens
            print(f"   📊 Tokens: {response.usage.prompt_tokens} in / "
                  f"{response.usage.completion_tokens} out "
                  f"(total: {response.usage.total_tokens} | session: {self.total_tokens_used})")

        return self._strip_think_tags(response.choices[0].message.content)

    def get_model_name(self) -> str:
        return self.model_name


# ── Anthropic ─────────────────────────────────────────────────────────────────
# NOTE: uses base class asyncio.to_thread async — true async client is future debt

class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model_name: str = "claude-sonnet-4-6"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model_name = model_name
        self.total_tokens_used = 0

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((anthropic.RateLimitError, anthropic.InternalServerError))
    )
    def generate(self, prompt: str, system_prompt: str = "", max_tokens: int = 8192) -> str:
        kwargs = {
            "model": self.model_name,
            "max_tokens": max_tokens,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        response = self.client.messages.create(**kwargs)
        if response.usage:
            self.total_tokens_used += response.usage.input_tokens + response.usage.output_tokens
            print(f"   📊 Tokens: {response.usage.input_tokens} in / "
                  f"{response.usage.output_tokens} out "
                  f"(total: {response.usage.input_tokens + response.usage.output_tokens}"
                  f" | session: {self.total_tokens_used})")

        return self._strip_think_tags(response.content[0].text)

    def get_model_name(self) -> str:
        return self.model_name


# ── Provider Factory ──────────────────────────────────────────────────────────

def _init_llm_provider(prefix: str = "") -> LLMProvider:
    """
    Initialise a provider instance for a given role prefix.

    prefix=""            → primary role   — reads LLM_PROVIDER, NVIDIA_MODEL, etc.
    prefix="EXTRACTION_" → extraction role — reads EXTRACTION_LLM_PROVIDER,
                           EXTRACTION_MODEL (flat, single key, no per-provider variants).

    For the extraction role, EXTRACTION_MODEL is required — it must be set
    explicitly in the configmap. There is no per-provider model fallback for
    extraction because the extraction role always targets one specific model.

    Auto-detect (LLM_PROVIDER=auto) is primary-only. Extraction role must be
    explicit — if EXTRACTION_LLM_PROVIDER is not set, the caller falls back to
    the primary instance without calling this function.
    """
    provider_type = os.getenv(f"{prefix}LLM_PROVIDER", "auto").lower()
    is_extraction = bool(prefix)

    # Auto-detect: primary role only
    if not is_extraction and provider_type in ("auto", ""):
        if os.getenv("NVIDIA_API_KEY"):
            provider_type = "nvidia"
        elif os.getenv("GROQ_API_KEY"):
            provider_type = "groq"
        elif os.getenv("GEMINI_API_KEY"):
            provider_type = "gemini"
        elif os.getenv("OPENAI_API_KEY"):
            provider_type = "openai"
        else:
            raise ValueError(
                "No LLM provider configured. Set LLM_PROVIDER and the corresponding "
                "API key (NVIDIA_API_KEY, GROQ_API_KEY, GEMINI_API_KEY, OPENAI_API_KEY). "
                "To use Anthropic, set LLM_PROVIDER=anthropic explicitly."
            )

    # Model resolution:
    # - Extraction role: flat EXTRACTION_MODEL, required.
    # - Primary role: per-provider env var with hardcoded default.
    if is_extraction:
        model_override = os.getenv(f"{prefix}MODEL")
        if not model_override:
            raise RuntimeError(
                f"{prefix}MODEL must be set when {prefix}LLM_PROVIDER is configured. "
                f"Add it to documind-configmap.yaml."
            )
    else:
        model_override = None  # each provider branch reads its own env var below

    role_label = "structured" if is_extraction else "primary"
    print(f"🔧 Initializing {role_label} LLM provider: {provider_type.upper()}")

    if provider_type == "nvidia":
        api_key = os.getenv("NVIDIA_API_KEY")
        if not api_key:
            raise RuntimeError(
                "NVIDIA_API_KEY is required for NVIDIA provider. "
                "Set it in your K8s secret."
            )
        model = model_override or os.getenv("NVIDIA_MODEL", "nvidia/llama-3.3-nemotron-super-49b-v1.5")
        instance = NvidiaProvider(api_key=api_key, model_name=model)

    elif provider_type == "groq":
        model = model_override or os.getenv("GROQ_MODEL", "qwen/qwen3-32b")
        instance = GroqProvider(
            api_key=os.getenv("GROQ_API_KEY"),
            model_name=model
        )

    elif provider_type == "openai":
        model = model_override or os.getenv("OPENAI_MODEL", "gpt-4o")
        instance = OpenAIProvider(
            api_key=os.getenv("OPENAI_API_KEY"),
            model_name=model
        )

    elif provider_type == "gemini":
        model = model_override or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        instance = GeminiProvider(
            api_key=os.getenv("GEMINI_API_KEY"),
            model_name=model
        )

    elif provider_type == "anthropic":
        model = model_override or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        instance = AnthropicProvider(
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            model_name=model
        )

    else:
        raise ValueError(
            f"Unknown provider '{provider_type}' for {prefix}LLM_PROVIDER. "
            f"Valid options: nvidia, groq, gemini, openai, anthropic"
        )

    print(f"✅ {role_label.capitalize()} LLM ready: {instance.get_model_name()}")
    return instance


# ── Singletons ────────────────────────────────────────────────────────────────
# Both initialised once at import time — no race condition possible.
# Extraction falls back to primary if EXTRACTION_LLM_PROVIDER is not set,
# preserving existing single-model behaviour with no config change required.

_primary_instance: LLMProvider = _init_llm_provider(prefix="")

if os.getenv("STRUCTURED_LLM_PROVIDER"):
    _extraction_instance: LLMProvider = _init_llm_provider(prefix="STRUCTURED_")
else:
    _extraction_instance: LLMProvider = _primary_instance


def get_llm_provider(role: str = "primary") -> LLMProvider:
    """
    Return the singleton LLM instance for the given role.

    role="primary"    → reasoning, generation, audit (nemotron-super by default)
    role="extraction" → graph extraction, coref, edge normalisation (qwen2.5-coder-32b)

    If EXTRACTION_LLM_PROVIDER is not configured, both roles return the same
    primary instance — safe default, no behaviour change for existing deployments.
    """
    if role == "extraction":
        print(f"♻️  Reusing extraction LLM instance ({_extraction_instance.get_model_name()})")
        return _extraction_instance
    print(f"♻️  Reusing primary LLM instance ({_primary_instance.get_model_name()})")
    return _primary_instance
