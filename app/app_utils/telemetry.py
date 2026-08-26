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

import logging
import os


def setup_pii_trace_redaction() -> None:
    """Attaches PiiRedactingSpanProcessor to the active OpenTelemetry TracerProvider.

    Prepends the processor so it executes before span exporters run.
    """
    redaction_enabled = os.environ.get("ENABLE_PII_REDACTION", "true").lower() == "true"
    redaction_mode = os.environ.get("PII_REDACTION_MODE", "traces_only").lower()

    if redaction_enabled and redaction_mode in ("traces_only", "both"):
        try:
            from opentelemetry import trace
            from opentelemetry.sdk.trace import TracerProvider
            from app.app_utils.span_processor import PiiRedactingSpanProcessor

            provider = trace.get_tracer_provider()
            if isinstance(provider, TracerProvider) and hasattr(provider, "_active_span_processor"):
                existing_types = [type(p) for p in provider._active_span_processor._span_processors]
                if PiiRedactingSpanProcessor not in existing_types:
                    processor = PiiRedactingSpanProcessor(enabled=True)
                    # Prepend processor so it redacts span attributes BEFORE exporters run
                    provider._active_span_processor._span_processors = (
                        processor,
                    ) + tuple(provider._active_span_processor._span_processors)
                    logging.info(
                        "OpenTelemetry PII redaction span processor attached as primary processor (mode: %s)",
                        redaction_mode,
                    )
        except Exception as e:
            logging.warning("Failed to register PiiRedactingSpanProcessor: %s", e)


def setup_telemetry() -> str | None:
    """Configure OpenTelemetry and GenAI telemetry standard for ADK otel_to_cloud integration."""

    # 1. Configurar OTEL_SERVICE_NAME para identificación en Cloud Trace
    os.environ.setdefault("OTEL_SERVICE_NAME", "biography-agent")

    # 2. Configurar convenciones semánticas de GenAI para captura de contenido y metadatos
    os.environ.setdefault("OTEL_SEMCONV_STABILITY_OPT_IN", "gen_ai_latest_experimental")
    os.environ.setdefault("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "SPAN_AND_EVENT")
    os.environ.setdefault("ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS", "true")


    commit_sha = os.environ.get("COMMIT_SHA", "dev")
    os.environ.setdefault(
        "OTEL_RESOURCE_ATTRIBUTES",
        f"service.name=biography_agent,service.namespace=biography_agent,service.version={commit_sha}",
    )

    bucket = os.environ.get("LOGS_BUCKET_NAME")
    if bucket:
        logging.info("Prompt-response GCS upload enabled - bucket: %s", bucket)
        os.environ.setdefault("OTEL_INSTRUMENTATION_GENAI_UPLOAD_FORMAT", "jsonl")
        os.environ.setdefault("OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK", "upload")
        path = os.environ.get("GENAI_TELEMETRY_PATH", "completions")
        os.environ.setdefault(
            "OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH",
            f"gs://{bucket}/{path}",
        )
    else:
        logging.info("Prompt-response logging (GCS) disabled (set LOGS_BUCKET_NAME to enable)")

    # Configurar modo de redacción PII en la inicialización básica
    setup_pii_trace_redaction()

    return bucket
