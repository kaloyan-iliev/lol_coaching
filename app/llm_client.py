"""
LLM client for the jungle coaching app.
Supports Gemini (default, cheapest for vision) and OpenAI.
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


def get_system_prompt(bible_override: str | None = None) -> str:
    """Build the full system prompt with the Jungle Bible injected."""
    bible = bible_override or JUNGLE_BIBLE
    if not bible:
        bible = "(No coaching guide loaded yet. Give your best general coaching advice.)"
    return PROMPT_TEMPLATE.format(jungle_bible=bible)


# --- Gemini ---

def _get_gemini_model():
    import google.generativeai as genai
    genai.configure(api_key=config.GEMINI_API_KEY)
    return genai.GenerativeModel(
        config.VISION_MODEL,
        system_instruction=get_system_prompt(),
    )


def analyze_screenshot_gemini(image_bytes: bytes, question: str) -> str:
    """Analyze a screenshot using Gemini vision."""
    import google.generativeai as genai

    model = _get_gemini_model()

    response = model.generate_content(
        [
            {"mime_type": "image/png", "data": image_bytes},
            f"Player's question: {question}",
        ],
        generation_config=genai.GenerationConfig(
            temperature=0.4,
            max_output_tokens=2000,
        ),
    )
    return response.text


def ask_question_gemini(question: str) -> str:
    """Answer a coaching question (no screenshot)."""
    import google.generativeai as genai

    model = _get_gemini_model()

    response = model.generate_content(
        f"Player's question: {question}",
        generation_config=genai.GenerationConfig(
            temperature=0.4,
            max_output_tokens=2000,
        ),
    )
    return response.text


# --- OpenAI ---

def analyze_screenshot_openai(image_bytes: bytes, question: str) -> str:
    """Analyze a screenshot using OpenAI vision."""
    import base64
    import openai

    client = openai.OpenAI(api_key=config.OPENAI_API_KEY)
    b64_image = base64.b64encode(image_bytes).decode("utf-8")

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": get_system_prompt()},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64_image}"},
                    },
                    {"type": "text", "text": f"Player's question: {question}"},
                ],
            },
        ],
        temperature=0.4,
        max_tokens=2000,
    )
    return response.choices[0].message.content


def ask_question_openai(question: str) -> str:
    """Answer a coaching question (no screenshot) using OpenAI."""
    import openai

    client = openai.OpenAI(api_key=config.OPENAI_API_KEY)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": get_system_prompt()},
            {"role": "user", "content": f"Player's question: {question}"},
        ],
        temperature=0.4,
        max_tokens=2000,
    )
    return response.choices[0].message.content


# --- Public interface ---

def analyze_screenshot(image_bytes: bytes, question: str = "What should I do here?") -> str:
    """Analyze a game screenshot and return coaching advice."""
    if config.LLM_PROVIDER == "gemini":
        return analyze_screenshot_gemini(image_bytes, question)
    elif config.LLM_PROVIDER == "openai":
        return analyze_screenshot_openai(image_bytes, question)
    else:
        raise ValueError(f"Unknown LLM provider: {config.LLM_PROVIDER}")


def ask_question(question: str) -> str:
    """Answer a coaching question without a screenshot."""
    if config.LLM_PROVIDER == "gemini":
        return ask_question_gemini(question)
    elif config.LLM_PROVIDER == "openai":
        return ask_question_openai(question)
    else:
        raise ValueError(f"Unknown LLM provider: {config.LLM_PROVIDER}")
