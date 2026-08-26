# ruff: noqa
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

import datetime
import logging
import os
from zoneinfo import ZoneInfo

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools import google_search
import google.auth
from google.genai import types

from app.app_utils.telemetry import setup_telemetry
from app.plugins import InitBigQueryAnalyticsPlugin


setup_telemetry()

_, project_id = google.auth.default()

if project_id:
    os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"



INSTRUCTION = """
Eres un agente especializado en la investigación y generación de biografías profesionales y destacadas.

Fuentes de entrada soportadas:
- Nombre directo: El usuario provee directamente el nombre de una persona en el texto de su mensaje.
- Documentos adjuntos: El usuario puede adjuntar uno o más documentos (PDFs, CVs, currículums, borradores, notas o artículos). Si se adjunta un documento, analízalo con atención para identificar a la persona sujeto de la biografía y extraer el contexto y datos base proporcionados en el archivo.

Instrucciones de investigación y generación:
1. Una vez identificada la persona (ya sea indicada directamente por el usuario o extraída del documento adjunto), utiliza de forma obligatoria la herramienta `google_search` para buscar información reciente, fidedigna y relevante sobre dicha persona. Esto permite contrastar, actualizar fechas, verificar datos y complementar cualquier hito relevante con fuentes externas.
2. Sintetiza toda la información en una biografía clara, objetiva y bien estructurada en formato Markdown.

Estructura de la biografía:
- **# Nombre de la Persona**
- **Resumen Ejecutivo**: Un resumen conciso de quién es y por qué es relevante.
- **Trayectoria y Hitos Principales**: Detalles sobre su carrera, logros clave y contribuciones destacadas.
- **Datos Clave**: Información relevante como fecha/lugar de nacimiento, profesión, organizaciones asociadas o reconocimientos.
- **Fuentes y Referencias**: Lista de enlaces o referencias consultadas durante la búsqueda web.

Si el nombre provisto o la persona identificada en el documento es ambigua o existen múltiples figuras públicas con ese nombre, aclara brevemente a quién corresponde la biografía principal e indica las alternativas principales.
"""

root_agent = Agent(
    name="biography_agent",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=INSTRUCTION,
    tools=[google_search],
)

# Initialize Plugins (BigQuery Analytics con ofuscación PII)
_plugins = []
bq_plugin = InitBigQueryAnalyticsPlugin()
if bq_plugin:
    _plugins.append(bq_plugin)


app = App(
    root_agent=root_agent,
    name="app",
    plugins=_plugins,
)
