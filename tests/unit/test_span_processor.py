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

"""Unit tests for PiiRedactingSpanProcessor."""

from unittest.mock import MagicMock
import pytest
from opentelemetry.sdk.trace import Event, ReadableSpan
from app.app_utils.span_processor import PiiRedactingSpanProcessor


class MockSpan:
    """Mock OpenTelemetry span for testing PiiRedactingSpanProcessor."""

    def __init__(self, attributes=None, events=None, name="test_span"):
        self.name = name
        self._attributes = attributes if attributes is not None else {}
        self._events = events if events is not None else []

    @property
    def attributes(self):
        return self._attributes

    @property
    def events(self):
        return self._events


class MockLlmRequestObj:
    def __init__(self, text):
        self.text = text

    def __str__(self):
        return f"LlmRequest(content='{self.text}')"


def test_span_processor_attributes_redaction():
    wrapped = MagicMock()
    processor = PiiRedactingSpanProcessor(wrapped_processor=wrapped, enabled=True)

    span = MockSpan(
        attributes={
            "gen_ai.prompt": "User email is john.doe@example.com and phone is 555-123-4567",
            "gen_ai.completion": "SSN 123-45-6789 and IP 192.168.1.1",
            "token_count": 42,
            "is_valid": True,
            "tags": ["email: alice@test.com", "clean_tag"],
        }
    )

    processor.on_end(span)

    assert "[REDACTED_EMAIL]" in span.attributes["gen_ai.prompt"]
    assert "[REDACTED_PHONE]" in span.attributes["gen_ai.prompt"]
    assert "john.doe@example.com" not in span.attributes["gen_ai.prompt"]

    assert "[REDACTED_SSN]" in span.attributes["gen_ai.completion"]
    assert "[REDACTED_IP_ADDRESS]" in span.attributes["gen_ai.completion"]

    assert span.attributes["token_count"] == 42
    assert span.attributes["is_valid"] is True
    assert "[REDACTED_EMAIL]" in span.attributes["tags"][0]

    wrapped.on_end.assert_called_once_with(span)


def test_span_processor_custom_object_redaction():
    wrapped = MagicMock()
    processor = PiiRedactingSpanProcessor(wrapped_processor=wrapped, enabled=True)

    obj = MockLlmRequestObj("Email user@domain.com, phone 555-987-6543")
    span = MockSpan(attributes={"gcp.vertex.agent.llm_request": obj})

    processor.on_end(span)

    redacted_val = span.attributes["gcp.vertex.agent.llm_request"]
    assert "[REDACTED_EMAIL]" in redacted_val
    assert "[REDACTED_PHONE]" in redacted_val
    assert "user@domain.com" not in redacted_val


def test_span_processor_events_redaction():
    wrapped = MagicMock()
    processor = PiiRedactingSpanProcessor(wrapped_processor=wrapped, enabled=True)

    event = Event(
        name="llm_call_event",
        attributes={"user_input": "Reach me at contact@company.org"},
        timestamp=1000000,
    )
    span = MockSpan(events=[event])

    processor.on_end(span)

    assert len(span.events) == 1
    assert span.events[0].attributes["user_input"] == "Reach me at [REDACTED_EMAIL]"


def test_span_processor_disabled():
    wrapped = MagicMock()
    processor = PiiRedactingSpanProcessor(wrapped_processor=wrapped, enabled=False)

    span = MockSpan(attributes={"email": "raw@test.com"})
    processor.on_end(span)

    assert span.attributes["email"] == "raw@test.com"
    wrapped.on_end.assert_called_once_with(span)


def test_span_processor_lifecycle_delegation():
    wrapped = MagicMock()
    processor = PiiRedactingSpanProcessor(wrapped_processor=wrapped, enabled=True)

    processor.on_start(MagicMock(), None)
    wrapped.on_start.assert_called_once()

    processor.shutdown()
    wrapped.shutdown.assert_called_once()

    processor.force_flush(1000)
    wrapped.force_flush.assert_called_once_with(1000)
