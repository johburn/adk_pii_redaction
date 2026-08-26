# bio-agent 🤖

Agente de generación de biografías factuales generado con **Google ADK 2.0 (Agent Development Kit)** y preparado para **Google Cloud Run**.

---

## 🏛️ Arquitectura del Sistema

Consulta la documentación detallada y diagramas en **[ARCHITECTURE.md](ARCHITECTURE.md)**.

```
bio-agent/
├── app/                        # Código principal del agente
│   ├── agent.py                # Lógica principal y herramientas (google_search)
│   ├── fast_api_app.py         # Servidor FastAPI y configuración de endpoints
│   └── app_utils/              # Gestión de sesiones y utilidades
│       ├── ensure_session_engine.py # Aprovisionamiento automático de Vertex AI Session Service
│       ├── telemetry.py        # Configuración de OpenTelemetry y Cloud Trace
│       └── types_def.py        # Definición de esquemas pydantic
├── tests/                      # Suite de pruebas unitarias y evalsets
│   └── eval/                   # Pruebas de evaluación con juez LLM
├── examples/                   # Ejemplos de uso (gestión de sesiones)
├── ARCHITECTURE.md             # Especificación técnica y diagramas de arquitectura
├── Makefile                    # Automatización de operaciones
├── .env.example                # Plantilla de variables de entorno
├── Dockerfile                  # Contenedor de producción
└── pyproject.toml              # Gestión de dependencias con uv
```

---

## 🚀 Comandos Rápidos (`Makefile`)

El proyecto incluye un `Makefile` para gestionar todo el ciclo de desarrollo y operaciones:

```bash
# Ver menú de ayuda con todos los comandos
make help
```

| Comando | Descripción |
|---|---|
| `make install` | Instala dependencias del proyecto usando `uv` |
| `make run` | Prueba rápida del agente en la terminal (`make run PROMPT="..."`) |
| `make test-remote` | Prueba el agente desplegado en Cloud Run |
| `make server` | Servidor FastAPI local en `http://localhost:8000` |
| `make playground` | Interfaz web interactiva (ADK Web Playground) |
| `make eval` | Ejecuta la evaluación con juez LLM |
| `make deploy` | Garantiza el Session Engine y despliega en **Cloud Run** |

---

## ⚙️ Variables de Entorno (`.env`)

Copia la plantilla `.env.example` a `.env` y configura tus credenciales:

```bash
cp .env.example .env
```

Variables clave:
- `GOOGLE_CLOUD_PROJECT`: ID del proyecto en GCP (`gke-service-project-081292`)
- `GOOGLE_CLOUD_LOCATION`: Región GCP (`us-central1`)
- `AGENT_ENGINE_ID`: ID del Reasoning Engine para sesiones en Vertex AI
- `BQ_ANALYTICS_DATASET_ID`: Dataset de analítica en BigQuery (`adk_agent_analytics`)

---

## 🔒 Redacción y Ofuscación de Datos Sensibles (PII Redaction)

El agente incorpora un mecanismo de seguridad y privacidad diseñado para detectar y ofuscar información de identificación personal (**PII**) antes de ser persistida o exportada a servicios externos de observabilidad.

### 🛡️ Datos Detectados y Patrones Regex
Los patrones de detección están definidos en [`DEFAULT_PII_PATTERNS`](app/plugins/pii_redaction_plugin.py#L29-L35) dentro de [`app/plugins/pii_redaction_plugin.py`](app/plugins/pii_redaction_plugin.py):
- **Correos Electrónicos**: `[REDACTED_EMAIL]`
- **Números Telefónicos**: `[REDACTED_PHONE]`
- **Tarjetas de Crédito**: `[REDACTED_CREDIT_CARD]`
- **Números de Seguro Social (SSN)**: `[REDACTED_SSN]`
- **Direcciones IP**: `[REDACTED_IP_ADDRESS]`

---

### 🔍 1. ¿Cómo funciona la Ofuscación en las Trazas (Cloud Trace / OpenTelemetry)?

Cuando el agente se ejecuta en Cloud Run, **ADK 2.0** y **FastAPI** instrumentan automáticamente las llamadas usando OpenTelemetry (`otel_to_cloud=True`). Sin un procesador de sanitización, las consultas del usuario y respuestas del modelo que contienen datos sensibles serían visibles en texto plano en la consola de **Google Cloud Trace**.

Para evitar esto:
1. **Inyección Prioritaria**: La función [`setup_pii_trace_redaction()`](app/app_utils/telemetry.py#L19-L48) en [`app/app_utils/telemetry.py`](app/app_utils/telemetry.py) obtiene el `TracerProvider` activo y antepone una instancia de [`PiiRedactingSpanProcessor`](app/app_utils/span_processor.py#L27-L125) al inicio de la lista `_span_processors`.
2. **Ejecución Antes de Exportadores**: Al estar ubicado como el primer procesador de la cadena, su método [`on_end(span)`](app/app_utils/span_processor.py#L78-L112) se ejecuta **antes** de que el exportador por lotes (`BatchSpanProcessor` / `CloudTraceSpanExporter`) serialice y envíe los spans a Google Cloud Trace.
3. **Sanitización de Atributos y Eventos**:
   - **`span._attributes`**: Itera recursivamente mediante [`_redact_val()`](app/app_utils/span_processor.py#L55-L76) sobre cadenas, listas, diccionarios y objetos complejos de ADK (tales como `LlmRequest` y `LlmResponse`), convirtiendo sus representaciones textuales y reemplazando cualquier patrón PII.
   - **`span._events`**: Reconstruye cada objeto `Event` saneando tanto el nombre del evento como todos sus atributos asociados.
4. **Resultado en Cloud Trace**: Los desarrolladores y auditores de observabilidad ven la jerarquía completa de spans, latencias y llamadas a herramientas, pero cualquier dato privado aparece como `[REDACTED_...]`.

Archivos clave:
- Procesador OpenTelemetry: [`app/app_utils/span_processor.py`](app/app_utils/span_processor.py)
- Registro e inicialización de telemetría: [`app/app_utils/telemetry.py`](app/app_utils/telemetry.py)
- Pruebas unitarias: [`tests/unit/test_span_processor.py`](tests/unit/test_span_processor.py)

---

### 📊 2. ¿Cómo funciona la Ofuscación en BigQuery (Agent Analytics)?

El agente utiliza el plugin oficial de ADK `BigQueryAgentAnalyticsPlugin` para registrar analítica de sesiones y eventos conversacionales en la tabla `agent_events` del dataset configurado (por defecto `adk_agent_analytics`).

Para asegurar que los logs persistidos en BigQuery no guarden PII sin anonimizar:
1. **Configuración de Formateador Personalizado**: En [`InitBigQueryAnalyticsPlugin()`](app/plugins/bigquery_analytics_plugin.py#L47-L80) dentro de [`app/plugins/bigquery_analytics_plugin.py`](app/plugins/bigquery_analytics_plugin.py), se configura `BigQueryLoggerConfig` pasando el formateador [`bq_pii_content_formatter`](app/plugins/bigquery_analytics_plugin.py#L34-L45).
2. **Interceptación de Contenido**: Cada vez que el agente registra un evento (mensaje de usuario, solicitud o respuesta al LLM, ejecución de herramientas):
   - Si el contenido es un diccionario, se serializa con `json.dumps()`.
   - Si es un objeto de ADK/GenAI (como `types.Content`), se convierte a cadena.
3. **Redacción Textual**: Se invoca [`_redactor.redact_text()`](app/plugins/pii_redaction_plugin.py#L54-L61), que ejecuta las expresiones regulares compiladas y reemplaza la información confidencial por los marcadores `[REDACTED_...]`.
4. **Inserción en BigQuery**: El plugin de ADK envía el payload ya sanitizado al servicio de streaming insert de BigQuery.

Archivos clave:
- Plugin e inicializador BigQuery: [`app/plugins/bigquery_analytics_plugin.py`](app/plugins/bigquery_analytics_plugin.py)
- Motor de redacción de texto: [`app/plugins/pii_redaction_plugin.py`](app/plugins/pii_redaction_plugin.py)
- Pruebas unitarias: [`tests/unit/test_bigquery_plugin.py`](tests/unit/test_bigquery_plugin.py)

---

### ⚙️ Modos de Configuración (`PII_REDACTION_MODE`)

| Variable | Opciones | Descripción |
|---|---|---|
| `ENABLE_PII_REDACTION` | `true` / `false` | Habilita o deshabilita globalmente el sistema de redacción. |
| `PII_REDACTION_MODE` | `traces_only` | **(Recomendado - Predeterminado)** Gemini recibe la información real intacta para procesar búsquedas y biografías con precisión, mientras que las trazas a **Cloud Trace** y los registros de **BigQuery Analytics** se guardan 100% ofuscados. |
| | `in_flight` | Activa [`PiiRedactionPlugin`](app/plugins/pii_redaction_plugin.py#L38-L123) en el ciclo de callbacks de ADK; ofusca los datos antes de que lleguen al modelo Gemini. |
| | `both` | Aplica redacción tanto en vuelo (LLM request/response) como en la exportación a Cloud Trace y BigQuery. |
| | `disabled` | Desactiva toda redacción. |

---


