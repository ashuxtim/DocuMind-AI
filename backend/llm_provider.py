import os
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from ollama import Client as OllamaClient
import openai
from google import genai

class LLMProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, system_prompt: str = "") -> str:
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        pass


class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str = None, requested_model: str = None):
        # If no URL provided, try Env Var, then fallback to host.docker.internal (for Docker), finally localhost
        if not base_url:
            base_url = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
        self.client = OllamaClient(host=base_url)
        
        # 1. AUTO-DETECT MODEL
        if not requested_model or requested_model == "auto":
            try:
                print(f"🕵️  Ollama: Auto-detecting best available model...")
                response = self.client.list()
                
                # Handle response.models (ListResponse object or dict)
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
                    # Prefer 'qwen' or 'llama', else pick first
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
        try:
            messages = []
            if system_prompt:
                messages.append({'role': 'system', 'content': system_prompt})
            messages.append({'role': 'user', 'content': prompt})

            response = self.client.chat(
                model=self.model_name,
                messages=messages,
                options={'temperature': 0}
            )
            return response.message.content
        except Exception as e:
            return f"Error generating response: {str(e)}"

    def get_model_name(self) -> str:
        return self.model_name

# --- VLLM PROVIDER (Cloud - FIXED) ---
class VLLMProvider(LLMProvider):
    def __init__(self, base_url: str, api_key: str = "EMPTY", requested_model: str = None):
        self.client = openai.OpenAI(
            base_url=base_url,
            api_key=api_key
        )
        self.context_window = 4096  # Standard context window (adjust if using larger models like 8k/32k)
        
        # 2. AUTO-DETECT MODEL (vLLM)
        try:
            print(f"🔗 Cloud: Connecting to {base_url}...")
            models_list = self.client.models.list()
            if models_list.data:
                self.model_name = models_list.data[0].id
                print(f"✅ Cloud: Connected to remote model -> '{self.model_name}'")
            else:
                self.model_name = requested_model or "unknown-model"
        except Exception as e:
            print(f"⚠️  Cloud Connection Warning: {e}")
            self.model_name = requested_model or "Qwen/Qwen2.5-14B-Instruct-AWQ"

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        try:
            # --- DYNAMIC TOKEN CALCULATION ---
            full_input = f"{system_prompt}\n{prompt}"
            # Rough estimate: 1 token ~= 3.5 chars
            estimated_input_tokens = len(full_input) / 3.5
            
            # Reserve space for the answer (buffer of 100 tokens)
            remaining_tokens = self.context_window - int(estimated_input_tokens) - 100
            
            if remaining_tokens < 100:
                print("⚠️ Warning: Input is very long, answer might be cut off.")
                max_tokens = 200 # Minimum viable answer
            else:
                # Ask for up to 1024, or whatever is left
                max_tokens = min(1024, remaining_tokens)

            messages = []
            if system_prompt:
                messages.append({'role': 'system', 'content': system_prompt})
            messages.append({'role': 'user', 'content': prompt})

            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=0,
                max_tokens=max_tokens # <--- DYNAMIC LIMIT
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"Error generating response (vLLM): {str(e)}"

    def get_model_name(self) -> str:
        return self.model_name

class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model_name: str = "gpt-4o"):
        self.client = openai.OpenAI(api_key=api_key)
        self.model_name = model_name

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        messages = []
        if system_prompt:
            messages.append({'role': 'system', 'content': system_prompt})
        messages.append({'role': 'user', 'content': prompt})
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=0
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"OpenAI Error: {e}"

    def get_model_name(self) -> str:
        return self.model_name

class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, model_name: str = "gemini-1.5-flash"):
        if not api_key:
            raise ValueError("Gemini API Key is missing. Set GEMINI_API_KEY in .env")
        
        genai.configure(api_key=api_key)
        self.model_name = model_name
        self.model = genai.GenerativeModel(model_name)

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        try:
            full_prompt = f"System: {system_prompt}\nUser: {prompt}" if system_prompt else prompt
            response = self.model.generate_content(full_prompt)
            return response.text
        except Exception as e:
            return f"Gemini Error: {e}"

    def get_model_name(self) -> str:
        return self.model_name

# --- GLOBAL SINGLETON CACHE ---
_llm_instance = None
_llm_lock = None

def get_llm_provider() -> LLMProvider:
    """
    Returns a SINGLETON instance to prevent loading model multiple times.
    Thread-safe with lazy initialization.
    """
    global _llm_instance, _llm_lock
    
    # If already initialized, return immediately
    if _llm_instance is not None:
        print("♻️  Reusing existing LLM instance")
        return _llm_instance
    
    # Initialize lock on first access (thread-safe)
    if _llm_lock is None:
        import threading
        _llm_lock = threading.Lock()
    
    # Acquire lock to prevent race conditions
    with _llm_lock:
        # Double-check after acquiring lock (another thread might have initialized)
        if _llm_instance is not None:
            return _llm_instance
        
        provider_type = os.getenv("LLM_PROVIDER", "ollama").lower()
        
        print(f"🔧 Initializing LLM Provider (SINGLETON): {provider_type}")
        
        if provider_type == "vllm":
            _llm_instance = VLLMProvider(
                requested_model=os.getenv("VLLM_MODEL"), 
                base_url=os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1"),
                api_key=os.getenv("VLLM_API_KEY", "EMPTY")
            )
        elif provider_type == "openai":
            _llm_instance = OpenAIProvider(
                api_key=os.getenv("OPENAI_API_KEY"),
                model_name=os.getenv("OPENAI_MODEL", "gpt-4o")
            )
        elif provider_type == "gemini":
            _llm_instance = GeminiProvider(
                api_key=os.getenv("GEMINI_API_KEY"),
                model_name=os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
            )
        elif provider_type == "ollama":
            _llm_instance = OllamaProvider(
                requested_model=os.getenv("OLLAMA_MODEL"), 
                base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            )
        else:
            print(f"⚠️  Unknown provider '{provider_type}', falling back to Ollama")
            _llm_instance = OllamaProvider()
        
        print(f"✅ LLM Provider initialized: {_llm_instance.get_model_name()}")
        return _llm_instance