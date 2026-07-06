"""
LLM client for the jungle coaching app.
Single entry point for all LLM calls (Gemini via google-genai, or OpenAI).

Public interface:
    generate_text(prompt, system=..., ...)   - text in, text out
    generate_vision(image_bytes, prompt, ...) - image + text in, text out
    analyze_screenshot(image_bytes, question) - screenshot coaching (uses Jungle Bible)
    ask_question(question)                    - coaching Q&A (uses Jungle Bible)
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config

# Load system prompt template
PROMPT_TEMPLATE = Path(
    os.path.join(os.path.dirname(__file__), "prompts", "system_prompt.txt")
).read_text(encoding="utf-8")

# Load the Jungle Bible if it exists
JUNGLE_BIBLE = ""
if os.path.exists(config.JUNGLE_BIBLE_FILE):
    JUNGLE_BIBLE = Path(config.JUNGLE_BIBLE_FILE).read_text(encoding="utf-8")


def load_house_rules() -> str:
    """The player's own coaching principles - highest-priority knowledge."""
    if os.path.exists(config.HOUSE_RULES_FILE):
        return Path(config.HOUSE_RULES_FILE).read_text(encoding="utf-8")
    return ""


def get_system_prompt(bible_override: str | None = None) -> str:
    """Build the full system prompt with house rules + the Jungle Bible injected."""
    bible = bible_override or JUNGLE_BIBLE
    if not bible:
        bible = "(No coaching guide loaded yet. Give your best general coaching advice.)"
    house_rules = load_house_rules()
    if house_rules:
        bible = (f"{house_rules}\n\n"
                 f"(The house rules above OVERRIDE anything below.)\n\n---\n\n{bible}")
    return PROMPT_TEMPLATE.format(jungle_bible=bible)


# --- Gemini (google-genai) ---

_gemini_client = None


def _gemini():
    global _gemini_client
    if _gemini_client is None:
        from google import genai
        _gemini_client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _gemini_client


def _gemini_config(system: str | None, temperature: float, max_tokens: int, json_mode: bool):
    from google.genai import types
    return types.GenerateContentConfig(
        system_instruction=system,
        temperature=temperature,
        max_output_tokens=max_tokens,
        response_mime_type="application/json" if json_mode else None,
    )


# --- Public interface ---

def _is_transient(err: Exception) -> bool:
    s = str(err)
    return any(code in s for code in ("429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE"))


def generate_text(
    prompt: str,
    system: str | None = None,
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 4000,
    json_mode: bool = False,
) -> str:
    """Send a text prompt to the configured LLM and return the response text.

    Gemini calls retry once after 20s on transient errors (503 spikes, RPM 429),
    then walk config.LLM_FALLBACK_MODELS (daily-quota 429s exhaust a model for
    the whole day, so retrying the same model is pointless)."""
    if config.LLM_PROVIDER == "gemini":
        import time

        models = [model or config.TEXT_MODEL]
        models += [m for m in getattr(config, "LLM_FALLBACK_MODELS", []) if m not in models]
        last_err = None
        for i, m in enumerate(models):
            for attempt in (1, 2):
                try:
                    response = _gemini().models.generate_content(
                        model=m,
                        contents=prompt,
                        config=_gemini_config(system, temperature, max_tokens, json_mode),
                    )
                    if i > 0:
                        print(f"  (note: generated with fallback model {m})")
                    return response.text
                except Exception as e:
                    if not _is_transient(e):
                        raise
                    last_err = e
                    if attempt == 1 and "RESOURCE_EXHAUSTED" not in str(e):
                        time.sleep(20)  # 503 spikes are usually short
                    else:
                        break  # daily quota / persistent - try next model
        raise last_err

    elif config.LLM_PROVIDER in ("openai", "openrouter"):
        import openai

        if config.LLM_PROVIDER == "openrouter":
            # OpenAI-compatible; free ":free" models = 50 req/day (1000 with a
            # one-time $10 credit purchase), 20 RPM
            client = openai.OpenAI(api_key=os.getenv("OPENROUTER_API_KEY"),
                                   base_url="https://openrouter.ai/api/v1")
            default_model = getattr(config, "OPENROUTER_MODEL", None)
        else:
            client = openai.OpenAI(api_key=config.OPENAI_API_KEY)
            default_model = "gpt-4o-mini"
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
        # Free OpenRouter variants throw transient upstream 429/503s - retry
        # with a wait instead of failing a whole batch run.
        import time as _time
        for attempt in range(4):
            try:
                response = client.chat.completions.create(
                    model=model or default_model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                )
                return response.choices[0].message.content
            except Exception as e:
                code = getattr(e, "status_code", None)
                if attempt == 3 or code not in (429, 500, 502, 503):
                    raise
                print(f"  (transient {code}, retrying in 45s...)")
                _time.sleep(45)

    raise ValueError(f"Unknown LLM provider: {config.LLM_PROVIDER}")


def generate_vision(
    image_bytes: bytes,
    prompt: str,
    system: str | None = None,
    model: str | None = None,
    temperature: float = 0.4,
    max_tokens: int = 2000,
) -> str:
    """Send an image + text prompt to the configured LLM and return the response text."""
    if config.LLM_PROVIDER == "gemini":
        from google.genai import types

        response = _gemini().models.generate_content(
            model=model or config.VISION_MODEL,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                prompt,
            ],
            config=_gemini_config(system, temperature, max_tokens, json_mode=False),
        )
        return response.text

    elif config.LLM_PROVIDER == "openai":
        import base64
        import openai

        client = openai.OpenAI(api_key=config.OPENAI_API_KEY)
        b64_image = base64.b64encode(image_bytes).decode("utf-8")
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_image}"}},
                {"type": "text", "text": prompt},
            ],
        })
        response = client.chat.completions.create(
            model=model or "gpt-4o-mini",
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content

    raise ValueError(f"Unknown LLM provider: {config.LLM_PROVIDER}")


def analyze_screenshot(image_bytes: bytes, question: str = "What should I do here?") -> str:
    """Analyze a game screenshot and return coaching advice."""
    return generate_vision(
        image_bytes,
        f"Player's question: {question}",
        system=get_system_prompt(),
    )


def ask_question(question: str) -> str:
    """Answer a coaching question without a screenshot."""
    return generate_text(
        f"Player's question: {question}",
        system=get_system_prompt(),
        temperature=0.4,
        max_tokens=2000,
    )
