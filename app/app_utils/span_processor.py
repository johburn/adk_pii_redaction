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

"""OpenTelemetry SpanProcessor for redacting PII from trace spans prior to export."""

import logging
import re
from typing import Any, Dict, Optional, Sequence

from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor, Event
from app.plugins.pii_redactor import DEFAULT_PII_PATTERNS, PiiRedactor

logger = logging.getLogger(__name__)


TARGET_ATTRIBUTE_KEYS = {
    "gen_ai.prompt",
    "gen_ai.completion",
    "gen_ai.system",
    "gcp.vertex.agent.llm_request",
    "gcp.vertex.agent.llm_response",
    "user_input",
    "user_message",
    "message",
    "messages",
    "prompt",
    "completion",
    "input",
    "output",
    "query",
    "tags",
}

TARGET_ATTRIBUTE_SUFFIXES = (
    ".prompt",
    ".completion",
    ".request",
    ".response",
    ".content",
    ".input",
    ".output",
    ".query",
    ".message",
    ".messages",
)


class PiiRedactingSpanProcessor(SpanProcessor):
    """OpenTelemetry SpanProcessor that inspects and redacts PII in span attributes

    and span events before passing spans to downstream processors or exporters.
    Optimized to selectively target user/LLM content attributes, bypassing technical telemetry.
    """

    def __init__(
        self,
        wrapped_processor: Optional[SpanProcessor] = None,
        patterns: Optional[Dict[str, str]] = None,
        enabled: bool = True,
        engine: Optional[str] = None,
        redactor: Optional[PiiRedactor] = None,
        token_format: Optional[str] = None,
    ) -> None:
        self.wrapped_processor = wrapped_processor
        self.enabled = enabled
        self.patterns = patterns if patterns is not None else DEFAULT_PII_PATTERNS
        self.redactor = redactor or PiiRedactor(
            engine=engine,
            enabled=enabled,
            patterns=self.patterns,
            token_format=token_format,
        )

    def redact_text(self, text: str) -> str:
        """Applies configured redactor (Cloud DLP / Regex) to replace PII in the given string."""
        if not text or not self.enabled:
            return text
        return self.redactor.redact_text(text)

    def _is_target_attribute(self, key: str) -> bool:
        """Determines if a span attribute is susceptible to containing sensitive user/LLM content."""
        if not key:
            return False
        key_lower = key.lower()
        if key_lower in TARGET_ATTRIBUTE_KEYS or key_lower.endswith(TARGET_ATTRIBUTE_SUFFIXES):
            return True
        return any(
            token in key_lower
            for token in (
                "prompt",
                "completion",
                "request",
                "response",
                "content",
                "message",
                "user",
                "query",
                "tag",
                "email",
                "phone",
                "pii",
            )
        )

    def _redact_val(self, val: Any, depth: int = 0, max_depth: int = 10) -> Any:
        if not self.enabled or val is None or depth > max_depth:
            return val

        if isinstance(val, str):
            return self.redact_text(val)
        elif isinstance(val, (list, tuple)):
            return [self._redact_val(v, depth + 1, max_depth) for v in val]
        elif isinstance(val, dict):
            return {k: self._redact_val(v, depth + 1, max_depth) for k, v in val.items()}
        elif isinstance(val, (int, float, bool)):
            return val
        else:
            # Handle custom objects (like LlmRequest, LlmResponse) attached to span attributes
            try:
                val_str = str(val)
                redacted_str = self.redact_text(val_str)
                if redacted_str != val_str:
                    return redacted_str
            except Exception as e:
                logger.debug("Failed to stringify object attribute: %s", e)
        return val


    def on_end(self, span: ReadableSpan) -> None:
        """Called when a span is ended. Redacts attributes and events on the span."""
        if not self.enabled:
            if self.wrapped_processor:
                self.wrapped_processor.on_end(span)
            return

        # Redact span attributes selectively
        if getattr(span, "_attributes", None) is not None:
            redacted_attributes = {}
            for key, val in span._attributes.items():
                if self._is_target_attribute(key):
                    redacted_attributes[key] = self._redact_val(val)
                else:
                    redacted_attributes[key] = val
            span._attributes = redacted_attributes


        # Redact span events if present
        if getattr(span, "_events", None) is not None:
            redacted_events = []
            for event in span._events:
                if hasattr(event, "attributes") and event.attributes:
                    event_attrs = {
                        k: self._redact_val(v) for k, v in event.attributes.items()
                    }
                    new_event = Event(
                        name=self.redact_text(event.name),
                        attributes=event_attrs,
                        timestamp=event.timestamp,
                    )
                    redacted_events.append(new_event)
                else:
                    redacted_events.append(event)
            span._events = redacted_events

        if self.wrapped_processor:
            self.wrapped_processor.on_end(span)

    def on_start(self, span: Any, parent_context: Any = None) -> None:
        if self.wrapped_processor:
            self.wrapped_processor.on_start(span, parent_context)

    def shutdown(self) -> None:
        if self.wrapped_processor:
            self.wrapped_processor.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        if self.wrapped_processor:
            return self.wrapped_processor.force_flush(timeout_millis)
        return True
