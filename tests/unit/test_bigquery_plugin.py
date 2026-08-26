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

"""Unit tests for BigQuery analytics plugin initialization helper."""

import os
from unittest.mock import MagicMock, patch
import pytest
from google.genai import types
from app.plugins.bigquery_analytics_plugin import (
    InitBigQueryAnalyticsPlugin,
    bq_pii_content_formatter,
)


def test_setup_bigquery_analytics_no_project():
    with patch.dict(os.environ, {}, clear=True):
        plugin = InitBigQueryAnalyticsPlugin()
        assert plugin is None


@patch("google.cloud.bigquery.Client")
def test_setup_bigquery_analytics_success(mock_bq_client):
    mock_client_inst = MagicMock()
    mock_bq_client.return_value = mock_client_inst

    with patch.dict(
        os.environ,
        {
            "GOOGLE_CLOUD_PROJECT": "test-project-123",
            "BQ_ANALYTICS_DATASET_ID": "test_dataset",
            "GOOGLE_CLOUD_LOCATION": "us-central1",
            "ENABLE_PII_REDACTION": "true",
            "PII_REDACTION_MODE": "traces_only",
        },
    ):
        plugin = InitBigQueryAnalyticsPlugin()
        assert plugin is not None
        assert plugin.config.content_formatter is not None
        mock_bq_client.assert_called_once_with(project="test-project-123")
        mock_client_inst.create_dataset.assert_called_once_with(
            "test-project-123.test_dataset", exists_ok=True
        )


@patch("google.cloud.bigquery.Client")
def test_setup_bigquery_analytics_exception_handled(mock_bq_client):
    mock_bq_client.side_effect = Exception("BigQuery connection failed")

    with patch.dict(os.environ, {"GOOGLE_CLOUD_PROJECT": "test-project-123"}):
        plugin = InitBigQueryAnalyticsPlugin()
        assert plugin is None


def test_bq_pii_content_formatter_dict():
    data = {
        "user_email": "alice@company.com",
        "phone": "555-123-4567",
        "nested": {"ip": "192.168.1.1"},
    }
    result = bq_pii_content_formatter(data, "user_event")
    assert "[REDACTED_EMAIL]" in result
    assert "[REDACTED_PHONE]" in result
    assert "[REDACTED_IP_ADDRESS]" in result
    assert "alice@company.com" not in result


def test_bq_pii_content_formatter_string():
    raw_str = "Contact john.doe@example.com or 555-987-6543"
    result = bq_pii_content_formatter(raw_str, "on_message")
    assert "[REDACTED_EMAIL]" in result
    assert "[REDACTED_PHONE]" in result


def test_bq_pii_content_formatter_content_obj():
    cnt = types.Content(
        role="user", parts=[types.Part.from_text(text="Send to bob@test.org")]
    )
    result = bq_pii_content_formatter(cnt, "model_request")
    assert "[REDACTED_EMAIL]" in result
    assert "bob@test.org" not in result


def test_bq_pii_content_formatter_none():
    assert bq_pii_content_formatter(None, "event") == ""
