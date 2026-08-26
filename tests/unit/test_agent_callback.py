import logging
import pytest
from unittest.mock import AsyncMock, MagicMock
from google.genai import types

from app.agent import before_agent_process_attachments_callback


@pytest.mark.asyncio
async def test_before_agent_callback_loads_artifacts_to_context(caplog):
    caplog.set_level(logging.INFO)

    mock_context = MagicMock()
    # Mensaje inicial solo con texto y un archivo inline
    inline_blob = types.Blob(
        data=b"%PDF-1.4 sample inline",
        mime_type="application/pdf",
        display_name="curriculum.pdf",
    )
    mock_context.user_content = types.Content(
        role="user",
        parts=[
            types.Part(text="Genera biografía"),
            types.Part(inline_data=inline_blob),
        ],
    )

    # Simular que en la sesión existen dos artefactos:
    # 1. curriculum.pdf (que ya viene inline, no se debe duplicar)
    # 2. notas_adicionales.txt (que solo está en ArtifactService y debe cargarse con load_artifact)
    mock_context.list_artifacts = AsyncMock(
        return_value=["curriculum.pdf", "notas_adicionales.txt"]
    )
    mock_context.save_artifact = AsyncMock(return_value=1)

    notas_part = types.Part(
        inline_data=types.Blob(
            data=b"Notas de trayectoria profesional...",
            mime_type="text/plain",
            display_name="notas_adicionales.txt",
        )
    )
    mock_context.load_artifact = AsyncMock(return_value=notas_part)

    result = await before_agent_process_attachments_callback(mock_context)

    # 1. El callback debe retornar None para que el agente continúe normalmente
    assert result is None

    # 2. Verificar que save_artifact se llamó para el archivo inline
    mock_context.save_artifact.assert_awaited_once()

    # 3. Verificar que load_artifact se ejecutó para notas_adicionales.txt
    mock_context.load_artifact.assert_awaited_once_with("notas_adicionales.txt")

    # 4. Verificar que notas_adicionales.txt se añadió a user_content.parts
    loaded_parts = [
        p for p in mock_context.user_content.parts
        if p.inline_data and getattr(p.inline_data, "display_name", None) == "notas_adicionales.txt"
    ]
    assert len(loaded_parts) == 1
    assert loaded_parts[0].inline_data.data == b"Notas de trayectoria profesional..."

    # 5. curriculum.pdf no debe estar duplicado
    cv_parts = [
        p for p in mock_context.user_content.parts
        if p.inline_data and getattr(p.inline_data, "display_name", None) == "curriculum.pdf"
    ]
    assert len(cv_parts) == 1

    # 6. Los logs deben reflejar la carga y persistencia
    log_text = caplog.text
    assert "curriculum.pdf" in log_text
    assert "notas_adicionales.txt" in log_text
    assert "[load_artifact] Cargando artefacto 'notas_adicionales.txt'" in log_text
