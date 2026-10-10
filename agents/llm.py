"""
agents/llm.py
─────────────────────────────────────────────────────────────────────────────
Gemini chat model shared by the pipeline nodes, the crawler and the eval.

Google stops serving older models to newly created API keys (a new key got
"gemini-2.5-flash is no longer available to new users"), so the model is
read from GEMINI_MODEL and can be changed without a code change.
─────────────────────────────────────────────────────────────────────────────
"""

import os

from dotenv import load_dotenv

load_dotenv()

GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
