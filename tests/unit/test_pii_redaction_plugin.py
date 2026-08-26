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

"""Unit tests for PiiRedactionPlugin."""

import pytest
from google.genai import types
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.agents.callback_context import CallbackContext

from app.plugins.pii_redaction_plugin import PiiRedactionPlugin


@pytest.fixture
def plugin():
    return PiiRedactionPlugin(enabled=True)


def test_redact_email(plugin):
    raw = "Contact me at john.doe@example.com for details."
    redacted = plugin.redact_text(raw)
    assert redacted == "Contact me at [REDACTED_EMAIL] for details."


def test_redact_phone(plugin):
    raw = "Call +1-555-123-4567 or 555.987.6543 today."
    redacted = plugin.redact_text(raw)
    assert "[REDACTED_PHONE]" in redacted
    assert "555-123-4567" not in redacted


def test_redact_ssn(plugin):
    raw = "SSN is 123-45-6789."
    redacted = plugin.redact_text(raw)
    assert redacted == "SSN is [REDACTED_SSN]."


def test_redact_ip_address(plugin):
    raw = "Server IP is 192.168.1.100."
    redacted = plugin.redact_text(raw)
    assert redacted == "Server IP is [REDACTED_IP_ADDRESS]."


def test_disabled_plugin():
    disabled_plugin = PiiRedactionPlugin(enabled=False)
    raw = "john.doe@example.com"
    assert disabled_plugin.redact_text(raw) == "john.doe@example.com"


@pytest.mark.asyncio
async def test_on_user_message_callback(plugin):
    msg = types.Content(
        role="user",
        parts=[types.Part.from_text(text="My email is alice@test.org")],
    )
    result = await plugin.on_user_message_callback(
        invocation_context=None, user_message=msg
    )
    assert result is not None
    assert result.parts[0].text == "My email is [REDACTED_EMAIL]"


from unittest.mock import MagicMock

@pytest.mark.asyncio
async def test_before_model_callback(plugin):
    content = types.Content(
        role="user",
        parts=[types.Part.from_text(text="User phone: 555-123-4567")],
    )
    request = LlmRequest(contents=[content])
    context = MagicMock()

    res = await plugin.before_model_callback(
        callback_context=context, llm_request=request
    )
    assert res is None  # Standard observation hook returns None
    assert request.contents[0].parts[0].text == "User phone: [REDACTED_PHONE]"


@pytest.mark.asyncio
async def test_after_model_callback(plugin):
    content = types.Content(
        role="model",
        parts=[types.Part.from_text(text="Generated email info: bob@company.com")],
    )
    response = LlmResponse(content=content)
    context = MagicMock()

    res = await plugin.after_model_callback(
        callback_context=context, llm_response=response
    )
    assert res is not None
    assert res.content.parts[0].text == "Generated email info: [REDACTED_EMAIL]"


@pytest.mark.asyncio
async def test_after_tool_callback(plugin):
    tool_result = {
        "status": "success",
        "details": {
            "contact_email": "support@service.com",
            "phones": ["123-456-7890", "987-654-3210"],
        },
        "count": 2,
    }

    res = await plugin.after_tool_callback(
        tool=None, tool_args={}, tool_context=None, result=tool_result
    )
    assert res["details"]["contact_email"] == "[REDACTED_EMAIL]"
    assert res["details"]["phones"] == ["[REDACTED_PHONE]", "[REDACTED_PHONE]"]
    assert res["count"] == 2
