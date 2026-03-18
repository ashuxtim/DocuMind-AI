import os
import re
import asyncio
from abc import ABC, abstractmethod
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from ollama import Client as OllamaClient
import openai
from google import genai
from google.genai import types
import groq
from groq import AsyncGroq


# ── Base Class ────────────────────────────────────────────────────────────────

class LLMProvider(ABC):

    # Fix 6 — <think> stripping moved to base class, available to all providers
    @staticmethod
    def _strip_think_tags(content: str) -> str:
        return re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()

    @abstractmethod
    def generate(self, prompt: str, system_prompt: str = "") -> str:
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        pass

    # Fix 1 — default async wrapper works for ALL providers immediately
    async def async_generate(self, prompt: str, system_prompt: str = "") -> str:
        return await asyncio.to_thread(self.generate, prompt, system_prompt)


# ── Groq ──────────────────────────────────────────────────────────────────────

class GroqProvider(LLMProvider):
    def __init__(self, api_key: str, model_name: str = "qwen/qwen3-32b"):
        self.client = groq.Groq(api_key=api_key)
        self.async_client = AsyncGroq(api_key=api_key)   # Fix 1 — true async client
        self.model_name = model_name
        self.total_tokens_used = 0                        # Fix 7 — token tracking

    def _build_messages(self, prompt: str, system_prompt: str) -> list:
        messages = []
        if system_prompt:
            messages.append({'role': 'system', 'content': system_prompt})
        messages.append({'role': 'user', 'content': prompt})
        return messages

    # Fix 2 — retry on transient errors, raises instead of returning error string
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((groq.RateLimitError, groq.InternalServerError))
    )
    def generate(self, prompt: str, system_prompt: str = "") -> str:
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=self._build_messages(prompt, system_prompt),
            temperature=0,
            max_tokens=4096
        )
        # Fix 7 — log token usage per call
        if response.usage:
            self.total_tokens_used += response.usage.total_tokens
            print(f"   📊 Tokens: {response.usage.prompt_tokens} in / "
                  f"{response.usage.completion_tokens} out "
                  f"(total: {response.usage.total_tokens} | session: {self.total_tokens_used})")

        return self._strip_think_tags(response.choices[0].message.content)  # Fix 6

    # Fix 1 — true async Groq implementation (not just asyncio.to_thread)
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((groq.RateLimitError, groq.InternalServerError))
    )
    async def async_generate(self, prompt: str, system_prompt: str = "") -> str:
        response = await self.async_client.chat.completions.create(
            model=self.model_name,
            messages=self._build_messages(prompt, system_prompt),
            temperature=0,
            max_tokens=4096
        )
        if response.usage:
            self.total_tokens_used += response.usage.total_tokens
            print(f"   📊 Tokens: {response.usage.prompt_tokens} in / "
                  f"{response.usage.completion_tokens} out "
                  f"(total: {response.usage.total_tokens} | session: {self.total_tokens_used})")

        return self._strip_think_tags(response.choices[0].message.content)  # Fix 6

    def get_model_name(self) -> str:
        return self.model_name


# ── Ollama ────────────────────────────────────────────────────────────────────

class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str = None, requested_model: str = None):
        if not base_url:
            base_url = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
        self.client = OllamaClient(host=base_url)

        if not requested_model or requested_model == "auto":
            try:
                print("🕵️  Ollama: Auto-detecting best available model...")
                response = self.client.list()
                models_data = getattr(response, 'models', []) or response.get('models', [])
                available_models = []
                for m in models_data:
                    name = None
                    if hasattr(m, 'model'):
                        name = m.model
                    elif hasattr(m, 'name'):
                        name = m.name
                    if not name and isinstance(m, dict):
                        name = m.get('model') or m.get('name')
                    if name:
                        available_models.append(name)

                if available_models:
                    preferred = next((m for m in available_models if "qwen" in m or "llama" in m), available_models[0])
                    self.model_name = preferred
                    print(f"✅ Ollama: Auto-selected model -> '{self.model_name}'")
                else:
                    print("⚠️  Ollama: No models found! Using default.")
                    self.model_name = "qwen2.5:7b"
            except Exception as e:
                print(f"⚠️  Ollama Detection Warning: {e}")
                self.model_name = "qwen2.5:7b"
        else:
            self.model_name = requested_model

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        messages = []
        if system_prompt:
            messages.append({'role': 'system', 'content': system_prompt})
        messages.append({'role': 'user', 'content': prompt})
        response = self.client.chat(
            model=self.model_name,
            messages=messages,
            options={'temperature': 0}
        )
        return self._strip_think_tags(response.message.content)  # Fix 6

    def get_model_name(self) -> str:
        return self.model_name


# ── vLLM ──────────────────────────────────────────────────────────────────────

class VLLMProvider(LLMProvider):
    def __init__(self, base_url: str, api_key: str = "EMPTY", requested_model: str = None):
        self.client = openai.OpenAI(base_url=base_url, api_key=api_key)
        self.context_window = 4096  # fallback default

        try:
            print(f"🔗 Cloud: Connecting to {base_url}...")
            models_list = self.client.models.list()
            if models_list.data:
                self.model_name = models_list.data[0].id
                # Fix 4 — auto-detect real context window from model metadata
                model_obj = models_list.data[0]
                ctx = getattr(model_obj, 'context_window', None) or \
                      getattr(model_obj, 'max_model_len', None)
                if ctx and isinstance(ctx, int):
                    self.context_window = ctx
                    print(f"✅ Context window detected: {self.context_window} tokens")
                print(f"✅ Cloud: Connected to remote model -> '{self.model_name}'")
            else:
                self.model_name = requested_model or "unknown-model"
        except Exception as e:
            print(f"⚠️  Cloud Connection Warning: {e}")
            self.model_name = requested_model or "Qwen/Qwen2.5-14B-Instruct-AWQ"

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        full_input = f"{system_prompt}\n{prompt}"
        # Fix 4 — use 4 chars/token (more conservative than 3.5)
        estimated_input_tokens = len(full_input) / 4
        remaining_tokens = self.context_window - int(estimated_input_tokens) - 100

        if remaining_tokens < 100:
            print("⚠️ Warning: Input is very long, answer might be cut off.")
            max_tokens = 200
        else:
            max_tokens = min(1024, remaining_tokens)

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
        return self._strip_think_tags(response.choices[0].message.content)  # Fix 6

    def get_model_name(self) -> str:
        return self.model_name


# ── OpenAI ────────────────────────────────────────────────────────────────────

class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model_name: str = "gpt-4o"):
        self.client = openai.OpenAI(api_key=api_key)
        self.model_name = model_name

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        messages = []
        if system_prompt:
            messages.append({'role': 'system', 'content': system_prompt})
        messages.append({'role': 'user', 'content': prompt})

        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=0
        )
        return self._strip_think_tags(response.choices[0].message.content)  # Fix 6

    def get_model_name(self) -> str:
        return self.model_name


# ── Gemini ────────────────────────────────────────────────────────────────────

class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, model_name: str = "gemini-2.0-flash"):
        if not api_key:
            raise ValueError("Gemini API Key is missing. Set GEMINI_API_KEY in .env")
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name

    # Fix 3 — use proper system_instruction param instead of plain text injection
    def generate(self, prompt: str, system_prompt: str = "") -> str:
        config = types.GenerateContentConfig(
            system_instruction=system_prompt if system_prompt else None,
            temperature=0
        )
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=config
        )
        return self._strip_think_tags(response.text)  # Fix 6

    def get_model_name(self) -> str:
        return self.model_name


# ── NVIDIA NIM ────────────────────────────────────────────────────────────────

class NvidiaProvider(LLMProvider):
    def __init__(self, api_key: str, model_name: str = "qwen/qwen2.5-coder-32b-instruct"):
        self.client = openai.OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=api_key
        )
        self.model_name = model_name
        self.total_tokens_used = 0  # Fix 7 — token tracking

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        messages = []
        if system_prompt:
            messages.append({'role': 'system', 'content': system_prompt})
        messages.append({'role': 'user', 'content': prompt})

        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=0,
            max_tokens=4096
        )
        # Fix 7 — log token usage
        if response.usage:
            self.total_tokens_used += response.usage.total_tokens
            print(f"   📊 Tokens: {response.usage.prompt_tokens} in / "
                  f"{response.usage.completion_tokens} out "
                  f"(total: {response.usage.total_tokens} | session: {self.total_tokens_used})")

        return self._strip_think_tags(response.choices[0].message.content)  # Fix 6

    def get_model_name(self) -> str:
        return self.model_name


# ── Singleton ─────────────────────────────────────────────────────────────────
# Fix 5 — true eager init at module import time, no lock needed, no race possible

def _init_llm_provider() -> LLMProvider:
    provider_type = os.getenv("LLM_PROVIDER", "auto").lower()

    if provider_type == "auto" or not provider_type:
        if os.getenv("NVIDIA_API_KEY"):
            provider_type = "nvidia"
        elif os.getenv("GROQ_API_KEY"):
            provider_type = "groq"
        elif os.getenv("GEMINI_API_KEY"):
            provider_type = "gemini"
        elif os.getenv("OPENAI_API_KEY"):
            provider_type = "openai"
        elif os.getenv("VLLM_BASE_URL"):
            provider_type = "vllm"
        else:
            provider_type = "ollama"

    print(f"🔧 Initializing LLM Provider: {provider_type.upper()}")

    if provider_type == "groq":
        instance = GroqProvider(
            api_key=os.getenv("GROQ_API_KEY"),
            model_name=os.getenv("GROQ_MODEL", "qwen/qwen3-32b")
        )
    elif provider_type == "nvidia":
        instance = NvidiaProvider(
            api_key=os.getenv("NVIDIA_API_KEY"),
            model_name=os.getenv("NVIDIA_MODEL", "qwen/qwen2.5-coder-32b-instruct")
        )
    elif provider_type == "vllm":
        instance = VLLMProvider(
            requested_model=os.getenv("VLLM_MODEL"),
            base_url=os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1"),
            api_key=os.getenv("VLLM_API_KEY", "EMPTY")
        )
    elif provider_type == "openai":
        instance = OpenAIProvider(
            api_key=os.getenv("OPENAI_API_KEY"),
            model_name=os.getenv("OPENAI_MODEL", "gpt-4o")
        )
    elif provider_type == "gemini":
        instance = GeminiProvider(
            api_key=os.getenv("GEMINI_API_KEY"),
            model_name=os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        )
    elif provider_type == "ollama":
        instance = OllamaProvider(
            requested_model=os.getenv("OLLAMA_MODEL"),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        )
    else:
        print(f"⚠️  Unknown provider '{provider_type}', falling back to Ollama")
        instance = OllamaProvider()

    print(f"✅ LLM Ready: {instance.get_model_name()}")
    return instance


# Initialized once at import time — no race condition possible
_llm_instance: LLMProvider = _init_llm_provider()


def get_llm_provider() -> LLMProvider:
    print("♻️  Reusing existing LLM instance")
    return _llm_instance