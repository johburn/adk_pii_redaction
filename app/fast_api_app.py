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

import os

import google.auth
from fastapi import FastAPI
from google.adk.cli.fast_api import get_fast_api_app

from app.app_utils.reasoning_engine_adapter import attach_reasoning_engine_routes
from app.app_utils.telemetry import setup_pii_trace_redaction, setup_telemetry

setup_telemetry()
_, project_id = google.auth.default()
allow_origins = (
    os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else None
)

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    web=True,
    allow_origins=allow_origins,
    otel_to_cloud=True,
)

# Inyecta procesador PII como primario en TracerProvider
setup_pii_trace_redaction()

app.title = "biography_agent"
app.description = "API for interacting with the Agent biography_agent"

# Rutas adaptadoras de Reasoning Engine para Gemini Enterprise y Console Playground
attach_reasoning_engine_routes(app)


# Main execution
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

