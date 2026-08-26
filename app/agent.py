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
from google.adk.agents.callback_context import CallbackContext
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

logger = logging.getLogger("app.agent")


async def before_agent_process_attachments_callback(
    callback_context: CallbackContext,
) -> types.Content | None:
    """Callback previo a la ejecución del agente.

    Inspecciona, persiste y carga archivos adjuntos y artefactos de la sesión
    directamente al contexto multimodal del agente (user_content.parts) mediante load_artifact.
    """
    user_content = callback_context.user_content
    existing_file_names: set[str] = set()

    # 1. Inspeccionar partes ya presentes en el mensaje del usuario
    if user_content and user_content.parts:
        for idx, part in enumerate(user_content.parts):
            if part.inline_data:
                blob = part.inline_data
                size_bytes = len(blob.data) if blob.data else 0
                file_name = getattr(blob, "display_name", None) or f"attachment_{idx + 1}"
                mime_type = blob.mime_type or "application/octet-stream"
                existing_file_names.add(file_name)
                logger.info(
                    "📎 [Adjunto en Mensaje - Inline] #%d | Nombre: %s | MIME: %s | Tamaño: %d bytes (%.2f KB)",
                    idx + 1,
                    file_name,
                    mime_type,
                    size_bytes,
                    size_bytes / 1024,
                )
    # 2. Si artifact_service está disponible, persistir y cargar artefactos al contexto
    artifact_service = getattr(
        getattr(callback_context, "_invocation_context", None),
        "artifact_service",
        None,
    )

    if artifact_service is not None:
        # 2a. Persistir en ArtifactService archivos que vengan inline si tienen nombre
        if user_content and user_content.parts:
            for part in user_content.parts:
                if part.inline_data:
                    blob = part.inline_data
                    fname = getattr(blob, "display_name", None)
                    if fname:
                        try:
                            await callback_context.save_artifact(fname, part)
                            logger.info("💾 [ArtifactService] Archivo '%s' guardado en sesión.", fname)
                        except Exception as save_err:
                            logger.debug("No se pudo persistir artefacto '%s': %s", fname, save_err)

        # 2b. Cargar artefactos de la sesión mediante load_artifact del ADK al contexto
        try:
            artifact_keys = await callback_context.list_artifacts()
            if artifact_keys:
                logger.info("📦 [Artefactos en Sesión] Total: %d | Claves: %s", len(artifact_keys), artifact_keys)
                for key in artifact_keys:
                    # Evitar duplicar si ya venía incluido en el mensaje inline
                    if key in existing_file_names:
                        continue

                    # Ejecutar load_artifact del ADK para cargar el archivo al contexto
                    artifact_part = await callback_context.load_artifact(key)
                    if artifact_part:
                        art_size = (
                            len(artifact_part.inline_data.data)
                            if artifact_part.inline_data and artifact_part.inline_data.data
                            else 0
                        )
                        art_mime = (
                            artifact_part.inline_data.mime_type
                            if artifact_part.inline_data
                            else (artifact_part.file_data.mime_type if artifact_part.file_data else "desconocido")
                        )
                        logger.info(
                            "📥 [load_artifact] Cargando artefacto '%s' (MIME: %s, Tamaño: %d bytes) al contexto del agente.",
                            key,
                            art_mime,
                            art_size,
                        )

                        # Inyectar el artefacto cargado en el contexto de la invocación
                        if user_content is not None:
                            if user_content.parts is None:
                                user_content.parts = []
                            user_content.parts.append(
                                types.Part(text=f"\n--- [Documento Adjunto Cargado: '{key}'] ---\n")
                            )
                            user_content.parts.append(artifact_part)
                            existing_file_names.add(key)
        except Exception as exc:
            logger.warning("Error al procesar/cargar artefactos con load_artifact: %s", exc)

    # Retornar None permite continuar con la ejecución regular del agente
    return None

root_agent = Agent(
    name="biography_agent",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=INSTRUCTION,
    tools=[google_search],
    before_agent_callback=before_agent_process_attachments_callback,
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
