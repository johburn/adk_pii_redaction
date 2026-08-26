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

"""Unit tests for PiiRedactor (Google Cloud DLP / SDP and Regex engines)."""

import os
from unittest.mock import MagicMock, patch
import pytest

from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from app.plugins.pii_redactor import PiiRedactor, PiiRedactionPlugin



def test_pii_redactor_regex_engine_redacted_format():
    redactor = PiiRedactor(engine="regex", token_format="redacted", enabled=True)
    text = "Email: john.doe@example.com, Phone: 555-123-4567, SSN: 123-45-6789"
    result = redactor.redact_text(text)

    assert "[REDACTED_EMAIL]" in result
    assert "[REDACTED_PHONE]" in result
    assert "[REDACTED_SSN]" in result
    assert "john.doe@example.com" not in result


def test_pii_redactor_regex_engine_infotype_format():
    redactor = PiiRedactor(engine="regex", token_format="info_type", enabled=True)
    text = "Contact alice@test.org or 555-987-6543, IP 10.0.0.1"
    result = redactor.redact_text(text)

    assert "[EMAIL_ADDRESS]" in result
    assert "[PHONE_NUMBER]" in result
    assert "[IP_ADDRESS]" in result
    assert "alice@test.org" not in result


def test_pii_redactor_disabled():
    redactor = PiiRedactor(enabled=False)
    text = "Secret email: bob@domain.com"
    assert redactor.redact_text(text) == text


@patch("google.cloud.dlp_v2.DlpServiceClient")
def test_pii_redactor_dlp_default_template(mock_dlp_class):
    mock_client = MagicMock()
    mock_dlp_class.return_value = mock_client

    mock_response = MagicMock()
    mock_response.item.value = "Redacted by Cloud DLP: [EMAIL_ADDRESS]"
    mock_client.deidentify_content.return_value = mock_response

    redactor = PiiRedactor(
        engine="dlp",
        project_id="test-project",
        location="us-central1",
        enabled=True,
    )

    text = "Contact me at user@google.com"
    result = redactor.redact_text(text)

    assert result == "Redacted by Cloud DLP: [EMAIL_ADDRESS]"
    mock_client.deidentify_content.assert_called_once()
    call_args = mock_client.deidentify_content.call_args[1]["request"]
    assert call_args["parent"] == "projects/test-project/locations/us-central1"
    assert call_args["item"]["value"] == text
    assert (
        call_args["deidentify_template_name"]
        == "projects/test-project/locations/us-central1/deidentifyTemplates/agent-template"
    )
    assert "inspect_config" in call_args


@patch("google.cloud.dlp_v2.DlpServiceClient")
def test_pii_redactor_dlp_inline_config(mock_dlp_class):
    mock_client = MagicMock()
    mock_dlp_class.return_value = mock_client

    mock_response = MagicMock()
    mock_response.item.value = "Redacted inline: [EMAIL_ADDRESS]"
    mock_client.deidentify_content.return_value = mock_response

    redactor = PiiRedactor(
        engine="dlp",
        project_id="test-project",
        location="global",
        deidentify_template="",
        enabled=True,
    )

    text = "Contact user@google.com"
    result = redactor.redact_text(text)

    assert result == "Redacted inline: [EMAIL_ADDRESS]"
    call_args = mock_client.deidentify_content.call_args[1]["request"]
    assert "deidentify_config" in call_args
    assert "inspect_config" in call_args


@patch("google.cloud.dlp_v2.DlpServiceClient")
def test_pii_redactor_dlp_with_template(mock_dlp_class):
    mock_client = MagicMock()
    mock_dlp_class.return_value = mock_client

    mock_response = MagicMock()
    mock_response.item.value = "Template output: [REDACTED]"
    mock_client.deidentify_content.return_value = mock_response

    redactor = PiiRedactor(
        engine="dlp",
        project_id="my-gcp-project",
        location="us-central1",
        deidentify_template="projects/my-gcp-project/locations/us-central1/deidentifyTemplates/tmpl123",
        inspect_template="projects/my-gcp-project/locations/us-central1/inspectTemplates/insp123",
        enabled=True,
    )

    result = redactor.redact_text("Sensitive user info")
    assert result == "Template output: [REDACTED]"

    call_args = mock_client.deidentify_content.call_args[1]["request"]
    assert call_args["parent"] == "projects/my-gcp-project/locations/us-central1"
    assert call_args["deidentify_template_name"] == "projects/my-gcp-project/locations/us-central1/deidentifyTemplates/tmpl123"
    assert call_args["inspect_template_name"] == "projects/my-gcp-project/locations/us-central1/inspectTemplates/insp123"



@patch("google.cloud.dlp_v2.DlpServiceClient")
def test_pii_redactor_hybrid_fallback_on_error(mock_dlp_class):
    mock_client = MagicMock()
    mock_dlp_class.return_value = mock_client
    mock_client.deidentify_content.side_effect = Exception("Cloud DLP API unavailable")

    redactor = PiiRedactor(
        engine="hybrid",
        project_id="test-project",
        token_format="info_type",
        enabled=True,
    )

    text = "Send backup to admin@corp.org and call 555-333-2222"
    result = redactor.redact_text(text)

    # Hybrid mode must fall back to regex safely without raising exception
    assert "[EMAIL_ADDRESS]" in result
    assert "[PHONE_NUMBER]" in result
    assert "admin@corp.org" not in result

    # Circuit breaker verification: second call should use regex directly without calling deidentify_content again
    result2 = redactor.redact_text("Contact ceo@company.com")
    assert "[EMAIL_ADDRESS]" in result2
    assert mock_client.deidentify_content.call_count == 1


def test_pii_redactor_empty_text():
    redactor = PiiRedactor()
    assert redactor.redact_text("") == ""
    assert redactor.redact_text(None) is None


# ------------------------------------------------------------------------------
# PiiRedactionPlugin & Callbacks Tests
# ------------------------------------------------------------------------------

@pytest.fixture
def plugin():
    return PiiRedactionPlugin(enabled=True, engine="regex")


def test_plugin_redact_primitives(plugin):
    assert "[REDACTED_EMAIL]" in plugin.redact_text("Contact me at john.doe@example.com")
    assert "[REDACTED_PHONE]" in plugin.redact_text("Call +1-555-123-4567")
    assert "[REDACTED_SSN]" in plugin.redact_text("SSN is 123-45-6789.")
    assert "[REDACTED_IP_ADDRESS]" in plugin.redact_text("Server IP is 192.168.1.100.")


def test_plugin_disabled():
    disabled_plugin = PiiRedactionPlugin(enabled=False)
    raw = "john.doe@example.com"
    assert disabled_plugin.redact_text(raw) == "john.doe@example.com"


@pytest.mark.asyncio
async def test_plugin_on_user_message_callback(plugin):
    msg = types.Content(
        role="user",
        parts=[types.Part.from_text(text="My email is alice@test.org")],
    )
    result = await plugin.on_user_message_callback(
        invocation_context=None, user_message=msg
    )
    assert result is not None
    assert result.parts[0].text == "My email is [REDACTED_EMAIL]"


@pytest.mark.asyncio
async def test_plugin_before_model_callback(plugin):
    content = types.Content(
        role="user",
        parts=[types.Part.from_text(text="User phone: 555-123-4567")],
    )
    request = LlmRequest(contents=[content])
    context = MagicMock()

    res = await plugin.before_model_callback(
        callback_context=context, llm_request=request
    )
    assert res is None
    assert request.contents[0].parts[0].text == "User phone: [REDACTED_PHONE]"


@pytest.mark.asyncio
async def test_plugin_after_model_callback(plugin):
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
async def test_plugin_after_tool_callback(plugin):
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


# ------------------------------------------------------------------------------
# PII Mode Configuration Tests
# ------------------------------------------------------------------------------

def test_traces_only_mode_config():
    with patch.dict(
        os.environ,
        {"ENABLE_PII_REDACTION": "true", "PII_REDACTION_MODE": "traces_only"},
    ):
        pii_enabled = os.environ.get("ENABLE_PII_REDACTION", "true").lower() == "true"
        pii_mode = os.environ.get("PII_REDACTION_MODE", "traces_only").lower()

        assert pii_enabled is True
        assert pii_mode == "traces_only"
        assert (pii_mode in ("in_flight", "both")) is False


def test_in_flight_mode_config():
    with patch.dict(
        os.environ,
        {"ENABLE_PII_REDACTION": "true", "PII_REDACTION_MODE": "in_flight"},
    ):
        pii_enabled = os.environ.get("ENABLE_PII_REDACTION", "true").lower() == "true"
        pii_mode = os.environ.get("PII_REDACTION_MODE", "traces_only").lower()

        assert pii_enabled is True
        assert pii_mode in ("in_flight", "both")


