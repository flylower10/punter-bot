"""
LLM client for personality-enhanced bot responses.

Thin wrapper around the Groq API. Returns enhanced text or None
(triggering template fallback in butler.py).
"""

import logging
from pathlib import Path

import requests
import yaml

from src.config import Config

logger = logging.getLogger(__name__)

_personality = None
_active_persona = None


def _load_personality():
    """Load personality config from YAML. Cached after first call."""
    global _personality
    if _personality is not None:
        return _personality

    config_path = Path(__file__).resolve().parent.parent / "config" / "personality.yaml"
    if not config_path.exists():
        logger.warning("personality.yaml not found at %s", config_path)
        _personality = {}
        return _personality

    with open(config_path, "r", encoding="utf-8") as f:
        _personality = yaml.safe_load(f) or {}
    logger.info("Loaded personality config with %d personas", len(_personality.get("personas", [])))
    return _personality


def get_active_persona():
    """Return the currently active persona dict, selecting one randomly if needed."""
    global _active_persona
    if _active_persona is not None:
        return _active_persona

    personality = _load_personality()
    personas = personality.get("personas", [])
    if not personas:
        return None

    _active_persona = random.choice(personas)
    logger.info("Selected persona for this period: %s", _active_persona.get("name", "Unknown"))
    return _active_persona


def reset_persona():
    """Force a new random persona selection (called at week start)."""
    global _active_persona
    _active_persona = None
    return get_active_persona()


def get_persona_hint():
    """Return the active persona's cryptic hint for the week-opening message."""
    persona = get_active_persona()
    if persona:
        return persona.get("hint", "")
    return ""


def _build_system_prompt(scenario=None, player_name=None):
    """
    Assemble the full system prompt from:
    1. Active persona's base prompt
    2. Global rules
    3. Player profile (if relevant)
    4. Non-player profile (if relevant)
    5. Scenario instruction (if relevant)
    """
    personality = _load_personality()
    persona = get_active_persona()
    if not persona:
        return None

    parts = [persona.get("system_prompt", "").strip()]

    rules = personality.get("rules", "")
    if rules:
        parts.append(f"\nRULES:\n{rules.strip()}")

    if player_name:
        profiles = personality.get("player_profiles", {})
        non_players = personality.get("non_players", {})
        profile = profiles.get(player_name) or non_players.get(player_name)
        if profile:
            parts.append(f"\nAbout {player_name}: {profile}")

    if scenario:
        scenarios = personality.get("scenarios", {})
        instruction = scenarios.get(scenario)
        if instruction:
            parts.append(f"\nSituation guidance: {instruction}")

    return "\n".join(parts)


def generate(context, scenario=None, player_name=None):
    """
    Generate an LLM-enhanced response.

    Args:
        context: A string describing what the bot needs to say (structured data,
                 not raw user input). E.g. "Pick confirmed for Edmund: Liverpool @ 3/4"
        scenario: Optional scenario key matching personality.yaml scenarios
        player_name: Optional formal first name for player-specific profile lookup

    Returns:
        Enhanced response string, or None if LLM is unavailable/disabled.
    """
    if not Config.LLM_ENABLED or not Config.GROQ_API_KEY:
        return None

    system_prompt = _build_system_prompt(scenario=scenario, player_name=player_name)
    if not system_prompt:
        return None

    personality = _load_personality()
    temperature = personality.get("temperature", 0.9)
    max_tokens = personality.get("max_tokens", 150)

    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {Config.GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": context},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=5,
        )

        if resp.status_code != 200:
            logger.warning("Groq API returned %d: %s", resp.status_code, resp.text[:200])
            return None

        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        if not content:
            return None

        logger.info("LLM response (%s): %s", get_active_persona().get("name", "?"), content[:100])
        return content

    except requests.Timeout:
        logger.warning("Groq API timed out")
        return None
    except Exception as e:
        logger.warning("Groq API error: %s", e)
        return None


