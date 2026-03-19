"""
LLM client for personality-enhanced bot responses.

Calls the Groq API and returns framing lines for the butler persona.
Returns a dict {"opening": "...", "closing": "..."} — never a full message.
Structured content is assembled by butler.py templates and is never touched here.

Falls back to {"opening": "", "closing": ""} on any failure so templates
render cleanly without any butler framing rather than breaking.
"""

import json
import logging
import re
from pathlib import Path

import requests
import yaml

from src.config import Config

logger = logging.getLogger(__name__)

_personality = None

# Fallback returned on any LLM failure — butler.py renders template only
_EMPTY_FRAMING = {"opening": "", "closing": ""}


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

    logger.info("Loaded personality config")
    return _personality


def _build_system_prompt(scenario=None, player_name=None):
    """
    Assemble the full system prompt from the YAML config:
      1. Character definition
      2. Voice rules
      3. Player or non-player profile (if relevant)
      4. Scenario guidance (if relevant)
      5. Output format instructions (always included)
    """
    personality = _load_personality()
    if not personality:
        return None

    parts = []

    character = personality.get("character", "").strip()
    if character:
        parts.append(character)

    voice = personality.get("voice", "").strip()
    if voice:
        parts.append(f"VOICE RULES:\n{voice}")

    if player_name:
        profiles = personality.get("player_profiles", {})
        non_players = personality.get("non_players", {})
        profile = profiles.get(player_name) or non_players.get(player_name)
        if profile:
            if isinstance(profile, dict):
                formal_name = profile.get("formal_name", player_name)
                relationship = profile.get("relationship", "")
                notes = profile.get("notes", "").strip()
                profile_text = f"Formal name: {formal_name}."
                if relationship:
                    profile_text += f" Relationship: {relationship}."
                if notes:
                    profile_text += f"\n{notes}"
            else:
                profile_text = str(profile)
            parts.append(f"PLAYER CONTEXT — {player_name}:\n{profile_text}")

    if scenario:
        scenarios = personality.get("scenarios", {})
        instruction = scenarios.get(scenario, "").strip()
        if instruction:
            parts.append(f"SITUATION — {scenario}:\n{instruction}")

    output_format = personality.get("output_format", "").strip()
    if output_format:
        parts.append(f"OUTPUT FORMAT:\n{output_format}")

    return "\n\n".join(parts)


def _parse_framing(content):
    """
    Parse the LLM response into {"opening": "...", "closing": "..."}.

    Handles:
      - Clean JSON: {"opening": "...", "closing": "..."}
      - JSON wrapped in markdown code fences
      - Malformed responses (returns empty framing)
    """
    if not content:
        return _EMPTY_FRAMING

    # Strip markdown code fences if present
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", content).strip()

    try:
        data = json.loads(cleaned)
        opening = str(data.get("opening", "")).strip()
        closing = str(data.get("closing", "")).strip()
        return {"opening": opening, "closing": closing}
    except (json.JSONDecodeError, AttributeError, TypeError):
        logger.warning("LLM returned non-JSON response: %s", content[:200])
        return _EMPTY_FRAMING


def generate(context, scenario=None, player_name=None):
    """
    Generate a free-form text response from the butler persona.

    Used by butler.py when the LLM should produce a full response (not just
    opening/closing framing). Falls back to empty string on any failure,
    which lets the caller use a template instead.

    Args:
        context:     Factual description or instruction for the LLM.
        scenario:    Key matching a scenario in personality.yaml.
        player_name: First name matching a player_profiles key.

    Returns:
        str — the LLM response text, or "" on failure.
    """
    if not Config.LLM_ENABLED or not Config.GROQ_API_KEY:
        return ""

    system_prompt = _build_system_prompt(scenario=scenario, player_name=player_name)
    if not system_prompt:
        return ""

    # Override output format: plain text, not JSON framing
    system_prompt += (
        "\n\nIMPORTANT: For this response, reply with plain text only. "
        "Do NOT return JSON. Write 1-2 sentences in character."
    )

    personality = _load_personality()
    temperature = personality.get("temperature", 0.7)
    max_tokens = personality.get("max_tokens", 120)
    model = personality.get("model", "llama-3.3-70b-versatile")

    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {Config.GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
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
            return ""

        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        # Strip any accidental JSON wrapping or code fences
        content = re.sub(r"```(?:json)?\s*|\s*```", "", content).strip()
        if content.startswith("{") and content.endswith("}"):
            try:
                parsed = json.loads(content)
                # LLM returned framing JSON despite instructions — combine it
                opening = str(parsed.get("opening", "")).strip()
                closing = str(parsed.get("closing", "")).strip()
                content = " ".join(filter(None, [opening, closing]))
            except (json.JSONDecodeError, AttributeError):
                pass
        logger.info("LLM generate: %s", content[:120])
        return content

    except requests.Timeout:
        logger.warning("Groq API timed out")
        return ""
    except Exception as e:
        logger.warning("Groq API error: %s", e)
        return ""



def get_framing(context, scenario=None, player_name=None):
    """
    Get opening and closing framing lines from the butler persona.

    Args:
        context:     What just happened — factual description for the LLM.
                     E.g. "Mr Kevin's pick, Liverpool @ 3/4, has won."
        scenario:    Key matching a scenario in personality.yaml
                     E.g. "result_win", "reminder_thursday", "week_complete"
        player_name: First name matching a player_profiles key in personality.yaml
                     E.g. "Kevin", "Edmund", "Brian"

    Returns:
        dict with keys "opening" and "closing" — both strings, either may be empty.
        Never raises. Falls back to empty framing on any failure.
    """
    if not Config.LLM_ENABLED or not Config.GROQ_API_KEY:
        return _EMPTY_FRAMING

    system_prompt = _build_system_prompt(scenario=scenario, player_name=player_name)
    if not system_prompt:
        return _EMPTY_FRAMING

    personality = _load_personality()
    temperature = personality.get("temperature", 0.7)
    max_tokens = personality.get("max_tokens", 120)
    model = personality.get("model", "llama-3.3-70b-versatile")

    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {Config.GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": context},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
            },
            timeout=5,
        )

        if resp.status_code != 200:
            logger.warning("Groq API returned %d: %s", resp.status_code, resp.text[:200])
            return _EMPTY_FRAMING

        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        framing = _parse_framing(content)
        logger.info("LLM framing — opening: %s | closing: %s",
                    framing["opening"][:80] if framing["opening"] else "(empty)",
                    framing["closing"][:80] if framing["closing"] else "(empty)")
        return framing

    except requests.Timeout:
        logger.warning("Groq API timed out")
        return _EMPTY_FRAMING
    except Exception as e:
        logger.warning("Groq API error: %s", e)
        return _EMPTY_FRAMING
