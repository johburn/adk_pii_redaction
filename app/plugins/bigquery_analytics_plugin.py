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

"""BigQuery Analytics Plugin initialization helper."""

import json
import logging
import os
from typing import Any, Optional

from google.adk.plugins.bigquery_agent_analytics_plugin import (
    BigQueryAgentAnalyticsPlugin,
    BigQueryLoggerConfig,
)
from google.cloud import bigquery
from app.plugins.pii_redactor import PiiRedactor

logger = logging.getLogger(__name__)

_redactor = PiiRedactor(enabled=True)



def bq_pii_content_formatter(event_content: Any, event_type: str) -> str:
    """Formats and redacts PII from content logged to BigQuery Analytics."""
    if event_content is None:
        return ""

    if isinstance(event_content, dict):
        text_content = json.dumps(event_content)
    else:
        text_content = str(event_content)

    return _redactor.redact_text(text_content)


def InitBigQueryAnalyticsPlugin() -> Optional[BigQueryAgentAnalyticsPlugin]:
    """Ensures BigQuery dataset exists and initializes BigQueryAgentAnalyticsPlugin with PII redaction."""
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    dataset_id = os.environ.get("BQ_ANALYTICS_DATASET_ID", "adk_agent_analytics")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-east1")

    if not project_id:
        return None

    try:
        bq = bigquery.Client(project=project_id)
        bq.create_dataset(f"{project_id}.{dataset_id}", exists_ok=True)

        redaction_enabled = os.environ.get("ENABLE_PII_REDACTION", "true").lower() == "true"
        redaction_mode = os.environ.get("PII_REDACTION_MODE", "traces_only").lower()

        content_formatter = None
        if redaction_enabled and redaction_mode in ("traces_only", "both"):
            content_formatter = bq_pii_content_formatter

        return BigQueryAgentAnalyticsPlugin(
            project_id=project_id,
            dataset_id=dataset_id,
            location=location,
            config=BigQueryLoggerConfig(
                content_formatter=content_formatter,
                gcs_bucket_name=os.environ.get("BQ_ANALYTICS_GCS_BUCKET"),
                connection_id=os.environ.get("BQ_ANALYTICS_CONNECTION_ID"),
            ),
        )
    except Exception as e:
        logger.warning(f"Failed to initialize BigQuery Analytics: {e}")
        return None


# Backward-compatible alias
setup_bigquery_analytics_plugin = InitBigQueryAnalyticsPlugin
