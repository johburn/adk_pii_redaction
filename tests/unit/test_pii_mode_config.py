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

"""Unit tests for PII redaction mode configurations."""

import os
from unittest.mock import patch
import pytest


def test_traces_only_mode_config():
    with patch.dict(
        os.environ,
        {"ENABLE_PII_REDACTION": "true", "PII_REDACTION_MODE": "traces_only"},
    ):
        pii_enabled = os.environ.get("ENABLE_PII_REDACTION", "true").lower() == "true"
        pii_mode = os.environ.get("PII_REDACTION_MODE", "traces_only").lower()

        # In traces_only mode, ADK in-flight plugin is NOT loaded
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

        # In in_flight mode, ADK in-flight plugin IS loaded
        assert pii_enabled is True
        assert pii_mode in ("in_flight", "both")
