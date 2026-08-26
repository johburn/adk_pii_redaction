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

"""Sensitive Data Protection (SDP / Cloud DLP) and Regex Redactor Module."""

import logging
import os
import re
from typing import Any, Dict, List, Optional

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

DEFAULT_DLP_INFOTYPES = [
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "PERSON_NAME",
    "CREDIT_CARD_NUMBER",
    "US_SOCIAL_SECURITY_NUMBER",
    "IP_ADDRESS",
]

REGEX_TO_INFOTYPE_MAP = {
    "EMAIL": "EMAIL_ADDRESS",
    "PHONE": "PHONE_NUMBER",
    "CREDIT_CARD": "CREDIT_CARD_NUMBER",
    "SSN": "US_SOCIAL_SECURITY_NUMBER",
    "IP_ADDRESS": "IP_ADDRESS",
}

DEFAULT_DLP_LOCATION = "us-central1"
DEFAULT_DLP_DEIDENTIFY_TEMPLATE = "agent-template"


class PiiRedactor:

    """Centralized PII redactor supporting Google Cloud DLP (SDP) and Regex engines."""

    def __init__(
        self,
        engine: Optional[str] = None,
        enabled: bool = True,
        project_id: Optional[str] = None,
        location: Optional[str] = None,
        info_types: Optional[List[str]] = None,
        deidentify_template: Optional[str] = None,
        inspect_template: Optional[str] = None,
        min_likelihood: Optional[str] = None,
        patterns: Optional[Dict[str, str]] = None,
        token_format: Optional[str] = None,
    ) -> None:
        self.enabled = enabled
        self.engine = (
            engine
            or os.environ.get("PII_ENGINE", "hybrid").lower()
        )
        self.project_id = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT")
        if not self.project_id:
            try:
                import google.auth
                _, default_proj = google.auth.default()
                self.project_id = default_proj
            except Exception:
                pass

        self.location = (
            location
            or os.environ.get("DLP_LOCATION")
            or os.environ.get("GOOGLE_CLOUD_LOCATION")
            or DEFAULT_DLP_LOCATION
        )

        # InfoTypes configuration
        if info_types is not None:
            self.info_types = info_types
        else:
            raw_types = os.environ.get("DLP_INFO_TYPES")
            if raw_types:
                self.info_types = [t.strip() for t in raw_types.split(",") if t.strip()]
            else:
                self.info_types = DEFAULT_DLP_INFOTYPES

        if deidentify_template is not None:
            self.deidentify_template = deidentify_template
        else:
            self.deidentify_template = os.environ.get(
                "DLP_DEIDENTIFY_TEMPLATE", DEFAULT_DLP_DEIDENTIFY_TEMPLATE
            )

        self.inspect_template = (
            inspect_template or os.environ.get("DLP_INSPECT_TEMPLATE")
        )
        self.min_likelihood = (
            min_likelihood or os.environ.get("DLP_MIN_LIKELIHOOD", "POSSIBLE")
        )



        # Regex fallback patterns
        self.patterns = patterns if patterns is not None else DEFAULT_PII_PATTERNS
        self._compiled_patterns = {
            key: re.compile(pat) for key, pat in self.patterns.items()
        }

        # Token format: 'info_type' ([EMAIL_ADDRESS]), 'redacted' ([REDACTED_EMAIL])
        self.token_format = (
            token_format
            or os.environ.get(
                "PII_TOKEN_FORMAT",
                "info_type" if self.engine == "dlp" else "redacted",
            ).lower()
        )


        self._dlp_client: Optional[Any] = None
        self._dlp_initialization_failed = False
        self._dlp_warning_logged = False
        self._dlp_service_unavailable = False


    def _get_dlp_client(self) -> Optional[Any]:
        """Lazily initializes the Google Cloud DLP client."""
        if self._dlp_client is not None:
            return self._dlp_client

        if self._dlp_initialization_failed:
            return None

        try:
            from google.cloud import dlp_v2
            self._dlp_client = dlp_v2.DlpServiceClient()
            return self._dlp_client
        except Exception as e:
            self._dlp_initialization_failed = True
            if not self._dlp_warning_logged:
                logger.warning(
                    "Google Cloud DLP client initialization failed, fallback active: %s",
                    e,
                )
                self._dlp_warning_logged = True
            return None

    def _redact_with_regex(self, text: str) -> str:
        """Applies configured regex patterns to replace PII in the string."""
        if not text:
            return text

        redacted = text
        for pii_type, regex in self._compiled_patterns.items():
            if self.token_format == "info_type":
                replacement = f"[{REGEX_TO_INFOTYPE_MAP.get(pii_type, pii_type)}]"
            else:
                replacement = f"[REDACTED_{pii_type}]"
            redacted = regex.sub(replacement, redacted)
        return redacted

    def _resolve_template_name(
        self, template: Optional[str], template_type: str = "deidentifyTemplates"
    ) -> Optional[str]:
        """Resolves a template ID or full resource name to a fully-qualified GCP resource path."""
        if not template:
            return None
        if template.startswith("projects/"):
            return template

        if self.location and self.location != "global":
            return f"projects/{self.project_id}/locations/{self.location}/{template_type}/{template}"
        return f"projects/{self.project_id}/{template_type}/{template}"

    def _redact_with_dlp(self, text: str) -> str:
        """Invokes Google Cloud DLP (SDP) deidentify_content API."""
        if not text or not self.project_id:
            return self._redact_with_regex(text)

        client = self._get_dlp_client()
        if client is None:
            raise RuntimeError("Cloud DLP client is not available")

        from google.cloud import dlp_v2

        parent = (
            f"projects/{self.project_id}/locations/{self.location}"
            if self.location and self.location != "global"
            else f"projects/{self.project_id}"
        )

        item = {"value": text}

        request: Dict[str, Any] = {
            "parent": parent,
            "item": item,
        }

        resolved_deid_tmpl = self._resolve_template_name(
            self.deidentify_template, "deidentifyTemplates"
        )
        if resolved_deid_tmpl:
            request["deidentify_template_name"] = resolved_deid_tmpl
        else:
            request["deidentify_config"] = {
                "info_type_transformations": {
                    "transformations": [
                        {
                            "primitive_transformation": {
                                "replace_with_info_type_config": {}
                            }
                        }
                    ]
                }
            }

        resolved_insp_tmpl = self._resolve_template_name(
            self.inspect_template, "inspectTemplates"
        )
        if resolved_insp_tmpl:
            request["inspect_template_name"] = resolved_insp_tmpl
        else:
            likelihood_enum = getattr(
                dlp_v2.Likelihood,
                self.min_likelihood.upper(),
                dlp_v2.Likelihood.LIKELY,
            )
            request["inspect_config"] = {
                "info_types": [{"name": it} for it in self.info_types],
                "min_likelihood": likelihood_enum,
            }


        response = client.deidentify_content(request=request)
        if response and response.item and response.item.value:
            return response.item.value
        return text

    def redact_text(self, text: str) -> str:
        """Redacts sensitive information from text according to configured engine."""
        if not text or not self.enabled:
            return text

        if self.engine == "regex":
            return self._redact_with_regex(text)

        if self.engine == "dlp":
            return self._redact_with_dlp(text)

        # Hybrid mode: attempt Cloud DLP, fallback to regex on any error
        if self._dlp_service_unavailable:
            return self._redact_with_regex(text)

        try:
            return self._redact_with_dlp(text)
        except Exception as e:
            self._dlp_service_unavailable = True
            if not self._dlp_warning_logged:
                logger.warning(
                    "Cloud DLP de-identification failed (%s). Falling back to Regex.",
                    e,
                )
                self._dlp_warning_logged = True
            return self._redact_with_regex(text)


class PiiRedactionPlugin(BasePlugin):
    """ADK Plugin that inspects and redacts PII across user messages, model inputs/outputs, and tool results."""

    def __init__(
        self,
        name: str = "pii_redaction_plugin",
        patterns: Optional[Dict[str, str]] = None,
        enabled: bool = True,
        engine: Optional[str] = None,
        redactor: Optional[PiiRedactor] = None,
        token_format: Optional[str] = None,
    ) -> None:
        super().__init__(name=name)
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


