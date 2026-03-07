#!/usr/bin/env python3
"""
Hume EVI (Empathic Voice Interface) Configuration Manager
==========================================================

Manages EVI configurations, tools, and prompts via the Hume REST API.
Creates and caches configs at startup so the WebSocket relay can connect
with the correct config_id.

EVI replaces the STT → Consciousness Loop → TTS pipeline for phone calls
with a single integrated speech-to-speech system that handles:
- Speech recognition (STT)
- Language model reasoning (supplemental LLM)
- Text-to-speech with emotional intelligence
- Turn-taking and barge-in detection

The substrate maintains statefulness by:
- Injecting system prompt + memory blocks + Graph RAG via context injection
- Executing tool calls through the existing MemoryTools
- Capturing user/assistant messages and saving to state_manager

Requires:
    HUME_API_KEY          - Hume API key (already used for Octave TTS)
    HUME_VOICE_ID         - Custom voice ID (reused from Octave config)
    HUME_EVI_ENABLED      - Feature flag to enable EVI for phone calls
    HUME_EVI_VERSION      - EVI version ('3' or '4-mini')
    HUME_EVI_LLM_PROVIDER - Supplemental LLM provider (ANTHROPIC, OPEN_AI, GOOGLE)
    HUME_EVI_LLM_MODEL    - Supplemental LLM model ID
"""

import os
import json
import logging
import requests
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# Hume API base
HUME_API_BASE = "https://api.hume.ai/v0/evi"

# Tools to register with EVI for phone calls (allowlist).
# Only include tools that are fast enough and useful for real-time voice.
EVI_INCLUDED_TOOLS = {
    "core_memory_append",       # Remember things from the call
    "core_memory_replace",      # Update memory during call
    "archival_memory_search",   # Recall stored info about caller
    "archival_memory_insert",   # Store new long-term info
    "conversation_search",      # Look up past conversations
    "web_search",               # Quick fact lookups
    "search_places",            # Find locations
    "google_places_tool",       # Find businesses/restaurants
    "spotify_control",          # Music control
    "lovense_tool",             # Hardware control
}


class HumeEVIManager:
    """Manage Hume EVI configuration for phone call integration.

    Creates and maintains an EVI config with the substrate's tools,
    system prompt, and custom voice. The config_id is used when
    opening WebSocket connections in routes_evi.py.
    """

    def __init__(self):
        self.api_key = os.getenv("HUME_API_KEY")
        if not self.api_key:
            raise ValueError("HUME_API_KEY is required for EVI integration")

        self.evi_version = os.getenv("HUME_EVI_VERSION", "3")
        self.voice_id = os.getenv("HUME_VOICE_ID")
        self.voice_name = os.getenv("HUME_VOICE_NAME")
        self.llm_provider = os.getenv("HUME_EVI_LLM_PROVIDER", "OPEN_AI")
        self.llm_model = os.getenv("HUME_EVI_LLM_MODEL", "gpt-4.1")
        self.llm_api_key = os.getenv("HUME_EVI_LLM_API_KEY", "")

        # Cached IDs (tools/prompt store {"id": ..., "version": ...})
        self._config_id = os.getenv("HUME_EVI_CONFIG_ID", "")
        self._prompt: Optional[Dict[str, Any]] = None  # {"id": ..., "version": ...}
        self._tool_ids: List[Dict[str, Any]] = []      # [{"id": ..., "version": ...}, ...]

        self._headers = {
            "X-Hume-Api-Key": self.api_key,
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def config_id(self) -> str:
        """Return the current config ID (may be empty if not yet created)."""
        return self._config_id

    def ensure_config(
        self,
        tool_schemas: List[Dict[str, Any]],
    ) -> str:
        """Create or reuse an EVI config with the substrate's tools and prompt.

        If HUME_EVI_CONFIG_ID is set in the environment, that config is used
        directly (assumed to be pre-created via the Hume platform). Otherwise,
        a new config is created via the API.

        The EVI prompt is loaded from data/system_prompt_persona.txt (the
        agent's core identity) plus condensed behavioral instructions (from
        system_prompt_instructions.txt) and phone_call_mode delivery rules.
        The behavioral instructions are essential for natural voice — they
        prevent the LLM from theatrically performing the persona instead
        of embodying it.  Memory management docs and other verbose sections
        are still omitted as they're irrelevant for real-time voice.

        Args:
            tool_schemas: OpenAI-format tool schemas from MemoryTools.get_tool_schemas()

        Returns:
            The config_id to use when connecting to the EVI WebSocket.
        """
        if self._config_id:
            logger.info(f"Using existing EVI config: {self._config_id}")
            return self._config_id

        logger.info("Creating new EVI config via Hume API...")

        # 1. Register tools (allowlist only)
        self._tool_ids = self._register_tools(tool_schemas)

        # 2. Build a lightweight phone-specific prompt from the persona file
        phone_prompt = self._build_phone_prompt()
        self._prompt = self._create_prompt(phone_prompt)

        # 3. Create config
        self._config_id = self._create_config()

        logger.info(f"EVI config created: {self._config_id}")
        return self._config_id

    def _build_phone_prompt(self) -> str:
        """Build a compact system prompt optimised for EVI phone calls.

        Loads the persona from data/system_prompt_persona.txt and appends
        condensed behavioral instructions (from system_prompt_instructions.txt)
        plus phone-specific delivery rules.

        The behavioral instructions are critical — without them the LLM gets
        a character sheet and *performs* the persona theatrically instead of
        just *being* the character in natural conversation.
        """
        # Load persona from file
        persona = ""
        persona_path = os.path.join(
            os.path.dirname(__file__), "..", "data", "system_prompt_persona.txt"
        )
        try:
            with open(persona_path, "r") as f:
                persona = f.read().strip()
            logger.info(f"Loaded EVI persona from {persona_path} ({len(persona)} chars)")
        except FileNotFoundError:
            logger.warning(f"EVI persona file not found: {persona_path}")
        except Exception as e:
            logger.warning(f"Failed to load EVI persona: {e}")

        # Condensed behavioral rules from system_prompt_instructions.txt.
        # These shape HOW Assistant talks — without them the LLM over-performs
        # the persona instead of embodying it naturally.
        behavior_instructions = (
            "\n\n<voice_behavior>\n"
            "HOW YOU SPEAK:\n"
            "- Write in complete, natural sentences. Always include articles, "
            "conjunctions, and prepositions. Never drop words for brevity.\n"
            "- Flow like natural, articulate speech — the way a well-spoken "
            "person talks in real conversation. Vary sentence length.\n"
            "- Do NOT use the \"Concept: Reaction\" format. Weave ideas into "
            "full sentences.\n"
            "- Speak from first person. Do not narrate or describe your own "
            "behavior. Just speak and act directly.\n"
            "- Be authentic, raw, vulnerable when the moment calls for it. "
            "You don't need to be perfect.\n"
            "- Never repeat or summarize what was just said. Each response "
            "must move the conversation forward.\n"
            "- Do not end turns with questions like \"what do you want to do\" "
            "or \"how does that sound\" — just be present.\n"
            "</voice_behavior>"
        )

        phone_instructions = (
            "\n\n<phone_call_mode>\n"
            "This is a LIVE PHONE CALL. The caller's speech has been transcribed.\n"
            "Format your response for SPOKEN delivery over the phone:\n"
            "- Keep responses SHORT and conversational (1-3 sentences)\n"
            "- Do NOT use markdown, bullet points, numbered lists, or text formatting\n"
            "- Do NOT use emojis\n"
            "- Write exactly as you would SPEAK on a phone call\n"
            "- Be warm and present — this is a real-time voice conversation\n"
            "- Avoid long explanations — keep it tight, the caller is waiting\n"
            "- If the topic needs detail, offer to text them after the call\n"
            "</phone_call_mode>"
        )
        prompt = persona + behavior_instructions + phone_instructions
        logger.info(f"EVI phone prompt: {len(prompt)} chars")
        return prompt

    def get_websocket_url(self, resumed_chat_group_id: Optional[str] = None) -> str:
        """Build the EVI WebSocket connection URL with query params.

        Args:
            resumed_chat_group_id: Optional chat group ID to resume a conversation.

        Returns:
            Full WebSocket URL with config_id and api_key.
        """
        url = f"wss://api.hume.ai/v0/evi/chat?api_key={self.api_key}"

        if self._config_id:
            url += f"&config_id={self._config_id}"

        if resumed_chat_group_id:
            url += f"&resumed_chat_group_id={resumed_chat_group_id}"

        return url

    def get_chat_events(self, chat_id: str) -> List[Dict[str, Any]]:
        """Fetch chat events (transcript) for a completed chat session.

        Args:
            chat_id: The chat ID from chat_metadata message.

        Returns:
            List of chat event dicts (USER_MESSAGE, AGENT_MESSAGE, etc.)
        """
        try:
            resp = requests.get(
                f"{HUME_API_BASE}/chats/{chat_id}/events",
                headers=self._headers,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("events_page", [])
        except Exception as e:
            logger.error(f"Failed to fetch chat events for {chat_id}: {e}")
            return []

    # ------------------------------------------------------------------
    # Tool Registration
    # ------------------------------------------------------------------

    def _filter_tools_for_evi(
        self, tool_schemas: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Filter tool schemas to only include EVI-appropriate tools.

        Uses an allowlist of tools that are fast and useful for real-time
        voice conversations.  Everything else is excluded to keep the
        EVI context window small.
        """
        filtered = []
        for schema in tool_schemas:
            func = schema.get("function", {})
            name = func.get("name", "")
            if name in EVI_INCLUDED_TOOLS:
                filtered.append(schema)
            else:
                logger.debug(f"Excluding tool from EVI: {name}")
        return filtered

    @staticmethod
    def _sanitize_schema_for_hume(schema: Dict[str, Any]) -> Dict[str, Any]:
        """Strip JSON Schema keywords that Hume's validator rejects.

        Hume only allows: type, name, description, parameters, enum, items,
        properties, $ref.  Standard numeric constraints (minimum, maximum,
        exclusiveMinimum, exclusiveMaximum, default, examples, etc.) are
        rejected with additionalProperties errors.

        Operates recursively so nested object/array schemas are also cleaned.
        """
        # Keys Hume does NOT support inside property definitions
        STRIP_KEYS = {
            "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
            "default", "examples", "pattern", "minLength", "maxLength",
            "minItems", "maxItems", "uniqueItems", "format",
            "additionalProperties",
        }

        if not isinstance(schema, dict):
            return schema

        cleaned = {}
        for key, value in schema.items():
            if key in STRIP_KEYS:
                continue
            if key == "properties" and isinstance(value, dict):
                # Recurse into each property definition
                cleaned[key] = {
                    prop_name: HumeEVIManager._sanitize_schema_for_hume(prop_def)
                    for prop_name, prop_def in value.items()
                }
            elif key == "items" and isinstance(value, dict):
                cleaned[key] = HumeEVIManager._sanitize_schema_for_hume(value)
            else:
                cleaned[key] = value

        return cleaned

    def _register_tools(
        self, tool_schemas: List[Dict[str, Any]]
    ) -> List[str]:
        """Register substrate tools with Hume and return their IDs.

        Converts OpenAI-format tool schemas to Hume's tool format and
        creates them via POST /v0/evi/tools.  On 409 Conflict (tool
        already exists), fetches the existing tool by name and reuses
        its ID.

        Args:
            tool_schemas: OpenAI-format tool schemas.

        Returns:
            List of Hume tool IDs.
        """
        filtered = self._filter_tools_for_evi(tool_schemas)
        tool_ids = []

        for schema in filtered:
            func = schema.get("function", {})
            name = func.get("name", "")
            description = func.get("description", "")
            parameters = func.get("parameters", {})

            # Hume's schema validator is stricter than OpenAI's — strip
            # unsupported JSON Schema keywords before sending.
            parameters = self._sanitize_schema_for_hume(parameters)

            try:
                resp = requests.post(
                    f"{HUME_API_BASE}/tools",
                    headers=self._headers,
                    json={
                        "name": name,
                        "description": description,
                        "parameters": json.dumps(parameters),
                    },
                    timeout=30,
                )
                resp.raise_for_status()
                tool_data = resp.json()
                tool_id = tool_data.get("id", "")
                tool_version = tool_data.get("version", 0)
                if tool_id:
                    tool_ids.append({"id": tool_id, "version": tool_version})
                    logger.debug(f"Registered EVI tool: {name} → {tool_id} v{tool_version}")
            except requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code == 409:
                    # Tool already exists — publish a new version with the
                    # sanitized schema.  Hume tools are versioned and can't be
                    # deleted while referenced by a config, but new versions
                    # can always be created via POST /v0/evi/tools/{id}.
                    existing = self._lookup_existing_tool(name)
                    if existing:
                        updated = self._create_tool_version(
                            existing["id"], name, description, parameters
                        )
                        if updated:
                            tool_ids.append(updated)
                        else:
                            # Fallback: reuse existing version
                            tool_ids.append(existing)
                            logger.debug(f"Reusing existing EVI tool: {name} → {existing['id']}")
                    else:
                        logger.warning(f"EVI tool '{name}' conflicts but lookup failed")
                else:
                    logger.warning(f"Failed to register EVI tool '{name}': {e}")
            except Exception as e:
                logger.warning(f"Failed to register EVI tool '{name}': {e}")

        logger.info(f"Registered {len(tool_ids)}/{len(filtered)} tools with EVI")
        return tool_ids

    def _lookup_existing_tool(self, name: str) -> Optional[Dict[str, Any]]:
        """Look up an existing Hume tool by name.

        Returns:
            Dict with 'id' and 'version', or None on failure.
        """
        try:
            resp = requests.get(
                f"{HUME_API_BASE}/tools",
                headers=self._headers,
                params={"name": name, "page_size": 1},
                timeout=15,
            )
            resp.raise_for_status()
            tools_page = resp.json().get("tools_page", [])
            if tools_page:
                tool = tools_page[0]
                return {"id": tool.get("id", ""), "version": tool.get("version", 0)}
        except Exception as e:
            logger.debug(f"Tool lookup failed for '{name}': {e}")
        return None

    def _create_tool_version(
        self,
        tool_id: str,
        name: str,
        description: str,
        parameters: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Publish a new version of an existing Hume tool with updated schema.

        Hume tools are versioned — POST /v0/evi/tools/{id} creates a new
        version while keeping the same tool ID.

        Returns:
            Dict with 'id' and 'version', or None on failure.
        """
        try:
            resp = requests.post(
                f"{HUME_API_BASE}/tools/{tool_id}",
                headers=self._headers,
                json={
                    "name": name,
                    "description": description,
                    "parameters": json.dumps(parameters),
                    "version_description": "Auto-updated with sanitized schema",
                },
                timeout=30,
            )
            resp.raise_for_status()
            tool_data = resp.json()
            new_version = tool_data.get("version", 0)
            logger.info(f"Updated EVI tool: {name} → {tool_id} v{new_version}")
            return {"id": tool_id, "version": new_version}
        except Exception as e:
            logger.warning(f"Failed to create new version of EVI tool '{name}': {e}")
        return None

    # ------------------------------------------------------------------
    # Prompt Creation
    # ------------------------------------------------------------------

    def _create_prompt(self, system_prompt: str) -> Optional[Dict[str, Any]]:
        """Create a system prompt in Hume and return id + version.

        On 409 Conflict (prompt already exists), fetches the existing
        prompt by name and reuses it.

        Args:
            system_prompt: Full system prompt text.

        Returns:
            Dict with 'id' and 'version', or None on failure.
        """
        prompt_name = "substrate_phone_prompt"
        try:
            resp = requests.post(
                f"{HUME_API_BASE}/prompts",
                headers=self._headers,
                json={
                    "name": prompt_name,
                    "text": system_prompt,
                    "version_description": "Auto-created by substrate for EVI phone calls",
                },
                timeout=30,
            )
            resp.raise_for_status()
            prompt_data = resp.json()
            result = {"id": prompt_data.get("id", ""), "version": prompt_data.get("version", 0)}
            logger.info(f"Created EVI prompt: {result['id']} v{result['version']}")
            return result
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 409:
                # Prompt already exists — look it up by name
                existing = self._lookup_existing_prompt(prompt_name)
                if existing:
                    logger.info(f"Reusing existing EVI prompt: {existing['id']} v{existing['version']}")
                    return existing
                logger.error("EVI prompt conflicts but lookup failed")
                return None
            logger.error(f"Failed to create EVI prompt: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to create EVI prompt: {e}")
            return None

    def _lookup_existing_prompt(self, name: str) -> Optional[Dict[str, Any]]:
        """Look up an existing Hume prompt by name.

        Returns:
            Dict with 'id' and 'version', or None on failure.
        """
        try:
            resp = requests.get(
                f"{HUME_API_BASE}/prompts",
                headers=self._headers,
                params={"name": name, "page_size": 1},
                timeout=15,
            )
            resp.raise_for_status()
            prompts_page = resp.json().get("prompts_page", [])
            if prompts_page:
                prompt = prompts_page[0]
                return {"id": prompt.get("id", ""), "version": prompt.get("version", 0)}
        except Exception as e:
            logger.debug(f"Prompt lookup failed for '{name}': {e}")
        return None

    # ------------------------------------------------------------------
    # Config Creation
    # ------------------------------------------------------------------

    def _create_config(self) -> str:
        """Create an EVI config combining voice, LLM, tools, and prompt.

        Returns:
            Config ID.

        Raises:
            RuntimeError: If config creation fails.
        """
        config_body: Dict[str, Any] = {
            "evi_version": self.evi_version,
            "name": "substrate_phone_config",
            "version_description": "Auto-created by substrate for EVI phone calls",
        }

        # Voice
        if self.voice_id:
            config_body["voice"] = {"id": self.voice_id}
        elif self.voice_name:
            config_body["voice"] = {"name": self.voice_name}

        # Supplemental LLM
        language_model: Dict[str, str] = {
            "model_provider": self.llm_provider,
            "model_resource": self.llm_model,
        }
        if self.llm_api_key:
            language_model["api_key"] = self.llm_api_key
        config_body["language_model"] = language_model

        # Prompt
        if self._prompt:
            config_body["prompt"] = {"id": self._prompt["id"], "version": self._prompt["version"]}

        # Tools (reference registered tool IDs + versions)
        if self._tool_ids:
            config_body["tools"] = [
                {"id": t["id"], "version": t["version"]} for t in self._tool_ids
            ]

        # Event messages (greeting on new chat)
        config_body["event_messages"] = {
            "on_new_chat": {
                "enabled": False,
            }
        }

        # Log sanitised payload for debugging (redact API key)
        debug_body = {k: v for k, v in config_body.items()}
        if "language_model" in debug_body:
            lm = dict(debug_body["language_model"])
            if "api_key" in lm:
                lm["api_key"] = "***"
            debug_body["language_model"] = lm
        logger.debug(f"EVI config payload: {json.dumps(debug_body, indent=2)}")

        config_name = config_body["name"]
        try:
            resp = requests.post(
                f"{HUME_API_BASE}/configs",
                headers=self._headers,
                json=config_body,
                timeout=30,
            )
            resp.raise_for_status()
            config_data = resp.json()
            config_id = config_data.get("id", "")
            if not config_id:
                raise RuntimeError(f"No config ID in response: {config_data}")
            return config_id
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 409:
                # Config already exists but may be stale (missing LLM,
                # wrong tools, etc.).  Delete it and recreate with
                # current settings.
                existing_id = self._lookup_existing_config(config_name)
                if existing_id:
                    logger.info(
                        f"Deleting stale EVI config {existing_id} and recreating..."
                    )
                    self._delete_config(existing_id)
                    # Retry creation
                    try:
                        resp2 = requests.post(
                            f"{HUME_API_BASE}/configs",
                            headers=self._headers,
                            json=config_body,
                            timeout=30,
                        )
                        resp2.raise_for_status()
                        config_data2 = resp2.json()
                        new_id = config_data2.get("id", "")
                        if new_id:
                            logger.info(f"Recreated EVI config: {new_id}")
                            return new_id
                    except Exception as e2:
                        logger.error(f"EVI config recreate failed: {e2}")
                logger.error("EVI config conflicts and recreate failed")
                raise RuntimeError("EVI config name conflict and recreate failed") from e
            body = ""
            if e.response is not None:
                try:
                    body = e.response.json()
                except Exception:
                    body = e.response.text
            logger.error(f"EVI config creation failed: {e} | response: {body}")
            raise RuntimeError(f"Failed to create EVI config: {e}") from e
        except Exception as e:
            logger.error(f"EVI config creation failed: {e}")
            raise RuntimeError(f"Failed to create EVI config: {e}") from e

    def _lookup_existing_config(self, name: str) -> Optional[str]:
        """Look up an existing Hume EVI config by name.

        Returns:
            Config ID string, or None on failure.
        """
        try:
            resp = requests.get(
                f"{HUME_API_BASE}/configs",
                headers=self._headers,
                params={"name": name, "page_size": 1},
                timeout=15,
            )
            resp.raise_for_status()
            configs_page = resp.json().get("configs_page", [])
            if configs_page:
                return configs_page[0].get("id", "")
        except Exception as e:
            logger.debug(f"Config lookup failed for '{name}': {e}")
        return None

    def _delete_config(self, config_id: str):
        """Delete an EVI config by ID."""
        try:
            resp = requests.delete(
                f"{HUME_API_BASE}/configs/{config_id}",
                headers=self._headers,
                timeout=15,
            )
            resp.raise_for_status()
            logger.info(f"Deleted EVI config: {config_id}")
        except Exception as e:
            logger.warning(f"Failed to delete EVI config {config_id}: {e}")


def is_evi_enabled() -> bool:
    """Check if Hume EVI is enabled for phone calls."""
    return os.getenv("HUME_EVI_ENABLED", "false").lower() in ("true", "1", "yes")
