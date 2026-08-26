"""
Ejemplo de Gestión de Sesiones con VertexAiSessionService en ADK 2.0
====================================================================
VertexAiSessionService utiliza Agent Platform Sessions (Vertex AI Reasoning Engine API)
para la persistencia gestionada de estados y sesiones.

Uso:
- Si estás en Agent Runtime, la plataforma asigna automáticamente el `reasoning_engine_id`.
- Si estás en Cloud Run o Local, puedes pasar `agent_engine_id` al instanciar el servicio.
"""

import asyncio
import os
import google.auth
from google.adk.sessions.vertex_ai_session_service import VertexAiSessionService

async def main():
    _, project_id = google.auth.default()
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-east1")
    
    # ID del recurso de Reasoning Engine / Agent Platform (si aplica)
    agent_engine_id = os.environ.get("AGENT_ENGINE_ID", "projects/123456789/locations/us-east1/reasoningEngines/987654321")

    print(f"Inicializando VertexAiSessionService...")
    print(f" - Proyecto: {project_id}")
    print(f" - Región: {location}")

    # Inicialización del cliente de sesiones
    session_service = VertexAiSessionService(
        project=project_id,
        location=location,
        agent_engine_id=agent_engine_id if "AGENT_ENGINE_ID" in os.environ else None
    )

    print("\n[Código de referencia para operaciones CRUD de Sesión]:")
    print("""
    # 1. Crear una sesión
    session = await session_service.create_session(
        app_name=agent_engine_id,
        user_id="usuario@ejemplo.com",
        state={"prefijo_idioma": "es", "historial": []}
    )

    # 2. Obtener una sesión existente
    session = await session_service.get_session(
        app_name=agent_engine_id,
        session_id=session.id
    )

    # 3. Listar sesiones del usuario
    sessions_list = await session_service.list_sessions(
        app_name=agent_engine_id,
        user_id="usuario@ejemplo.com"
    )

    # 4. Eliminar una sesión
    await session_service.delete_session(
        app_name=agent_engine_id,
        session_id=session.id
    )
    """)

if __name__ == "__main__":
    asyncio.run(main())
