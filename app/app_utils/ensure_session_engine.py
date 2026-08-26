import os
import sys
import logging
import requests
import google.auth
import google.auth.transport.requests

def ensure_session_engine(display_name: str = "biography_agent") -> str:

    """
    Retrieves or creates a ReasoningEngine instance via REST API
    and returns its full resource name.
    """
    creds, project_id = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    req = google.auth.transport.requests.Request()
    creds.refresh(req)
    token = creds.token

    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    url = f"https://{location}-aiplatform.googleapis.com/v1/projects/{project_id}/locations/{location}/reasoningEngines"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # 1. List existing reasoning engines via REST
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        engines = resp.json().get("reasoningEngines", [])
        for engine in engines:
            if engine.get("displayName") == display_name:
                resource_name = engine.get("name")
                sys.stderr.write(f"✓ ReasoningEngine dedicado encontrado: {resource_name}\n")
                return resource_name

    # 2. If not found, create a new reasoning engine via REST
    sys.stderr.write(f"No se encontró ReasoningEngine '{display_name}'. Creando...\n")
    body = {
        "displayName": display_name,
        "description": f"Dedicated session engine for {display_name} service"
    }
    resp = requests.post(url, headers=headers, json=body)
    resp_data = resp.json()

    if "name" in resp_data:
        resource_name = resp_data.get("name")
        if "operations" in resource_name:
            target = resp_data.get("metadata", {}).get("genericMetadata", {}).get("target") or resource_name
            resource_name = target
        sys.stderr.write(f"✓ Nuevo ReasoningEngine '{display_name}' creado: {resource_name}\n")
        return resource_name

    raise RuntimeError(f"Error al crear ReasoningEngine: {resp_data}")

if __name__ == "__main__":
    resource_name = ensure_session_engine()
    sys.stdout.write(resource_name + "\n")
