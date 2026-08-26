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

from app.plugins.pii_redactor import PiiRedactor


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
def test_pii_redactor_dlp_success(mock_dlp_class):
    mock_client = MagicMock()
    mock_dlp_class.return_value = mock_client

    mock_response = MagicMock()
    mock_response.item.value = "Redacted by Cloud DLP: [EMAIL_ADDRESS]"
    mock_client.deidentify_content.return_value = mock_response

    redactor = PiiRedactor(
        engine="dlp",
        project_id="test-project",
        location="global",
        enabled=True,
    )

    text = "Contact me at user@google.com"
    result = redactor.redact_text(text)

    assert result == "Redacted by Cloud DLP: [EMAIL_ADDRESS]"
    mock_client.deidentify_content.assert_called_once()
    call_args = mock_client.deidentify_content.call_args[1]["request"]
    assert call_args["parent"] == "projects/test-project"
    assert call_args["item"]["value"] == text
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

