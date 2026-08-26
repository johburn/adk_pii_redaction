# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""PII Redaction Plugin for ADK (Agent Development Kit)."""

import logging
import re
from typing import Any, Dict, Optional

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.plugins.base_plugin import BasePlugin
from google.genai import types

logger = logging.getLogger(__name__)

DEFAULT_PII_PATTERNS = {
    "EMAIL": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    "PHONE": r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
    "CREDIT_CARD": r"\b(?:\d[ -]*?){13,16}\b",
    "SSN": r"\b\d{3}-\d{2}-\d{4}\b",
    "IP_ADDRESS": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
}


class PiiRedactionPlugin(BasePlugin):
    """ADK Plugin that inspects and redacts PII across user messages, model inputs/outputs, and tool results."""

    def __init__(
        self,
        name: str = "pii_redaction_plugin",
        patterns: Optional[Dict[str, str]] = None,
        enabled: bool = True,
    ) -> None:
        super().__init__(name=name)
        self.enabled = enabled
        self.patterns = patterns if patterns is not None else DEFAULT_PII_PATTERNS
        self._compiled_patterns = {
            key: re.compile(pat) for key, pat in self.patterns.items()
        }

    def redact_text(self, text: str) -> str:
        """Applies configured regex patterns to replace PII in the given string."""
        if not text or not self.enabled:
            return text
        redacted = text
        for pii_type, regex in self._compiled_patterns.items():
            redacted = regex.sub(f"[REDACTED_{pii_type}]", redacted)
        return redacted

    def _redact_content(self, content: Optional[types.Content]) -> None:
        """Helper to redact text in all parts of a types.Content object in-place."""
        if not content or not hasattr(content, "parts") or not content.parts:
            return
        for part in content.parts:
            if hasattr(part, "text") and part.text:
                part.text = self.redact_text(part.text)

    async def on_user_message_callback(
        self, *, invocation_context: Any, user_message: types.Content
    ) -> Optional[types.Content]:
        """Intercepts incoming user messages and redacts PII before processing."""
        if not self.enabled or not user_message:
            return None
        self._redact_content(user_message)
        return user_message

    async def before_model_callback(
        self, *, callback_context: CallbackContext, llm_request: LlmRequest
    ) -> Optional[LlmResponse]:
        """Intercepts model request and redacts PII in all content items prior to LLM call."""
        if not self.enabled or not llm_request:
            return None
        if hasattr(llm_request, "contents") and llm_request.contents:
            for content in llm_request.contents:
                self._redact_content(content)
        return None

    async def after_model_callback(
        self, *, callback_context: CallbackContext, llm_response: LlmResponse
    ) -> Optional[LlmResponse]:
        """Intercepts model response and redacts PII in generated output before returning to caller."""
        if not self.enabled or not llm_response:
            return None
        if hasattr(llm_response, "content") and llm_response.content:
            self._redact_content(llm_response.content)
        return llm_response

    async def after_tool_callback(
        self,
        *,
        tool: Any,
        tool_args: dict[str, Any],
        tool_context: Any,
        result: dict,
    ) -> Optional[dict]:
        """Intercepts tool execution results and redacts PII in string data structures."""
        if not self.enabled or not result:
            return None

        def _redact_obj(obj: Any) -> Any:
            if isinstance(obj, str):
                return self.redact_text(obj)
            elif isinstance(obj, dict):
                return {k: _redact_obj(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [_redact_obj(v) for v in obj]
            return obj

        return _redact_obj(result)
