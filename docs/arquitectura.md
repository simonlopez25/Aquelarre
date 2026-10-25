# Guía de arquitectura

Este documento describe la arquitectura del backend de Aquelarre.

## Visión general

Aquelarre es un orquestador local que unifica proveedores gratuitos de LLM detrás de un único endpoint compatible con OpenAI. Sigue una arquitectura limpia por capas para separar responsabilidades y facilitar el mantenimiento.

## Capas

### `domain/` — Lógica pura

Contiene toda la lógica de negocio que no requiere I/O: clasificación de tareas, router híbrido, cuotas y circuit breakers.

- `router.py` — Clasificación de tareas, decisiones de enrutamiento, gestión de cuotas.
- `schemas.py` — Esquemas de request/response compatibles con OpenAI.

**Reglas:**
- Nunca importa de `api/`, `infrastructure/` ni `main.py`.
- Sin red, sin disco, sin I/O.

### `core/` — Transversal

Configuración, logging, seguridad y errores. Depende solo de librerías externas.

- `config.py` — Configuración centralizada vía pydantic-settings.
- `security.py` — Verificación de API keys y redacción de secrets en logs.
- `errors.py` — Catálogo de errores bilingües.
- `logging_setup.py` — Configuración de logging con filtro de redacción.

**Reglas:**
- Solo importa de librerías externas y de `core/` mismo.
- Nada de `os.getenv` fuera de `config.py`.

### `api/` — Transporte HTTP

Rutas, manejo de errores y mappers. Sin lógica de negocio.

- `routes.py` — Endpoints HTTP.
- `handlers.py` — Manejadores de excepciones.
- `mappers.py` — Traducción entre payloads de proveedor y el contrato HTTP.

**Reglas:**
- Importa de `domain/` y `core/`, jamás de `infrastructure/` directamente.

### `infrastructure/` — Adaptadores externos

Base de datos, cliente LiteLLM y cualquier otra integración externa.

- `db.py` — Persistencia SQLite de usage records.
- `litellm_client.py` — Wrapper exception-free alrededor de LiteLLM.
- `errors.py` — Clasificación de fallos de proveedores.

### `main.py` — Composition root

Factory de la app, CORS, lifespan. No contiene lógica de negocio.

## Flujo de una request

1. El cliente envía `POST /v1/chat/completions` con `Authorization: Bearer <API_KEY>`.
2. `verify_api_key` valida la credencial con `hmac.compare_digest`.
3. `chat_completions` delega en `HybridRouter.decide()` para elegir un proveedor.
4. `LiteLLMClient.complete()` llama al proveedor a través de LiteLLM.
5. El resultado se mapea a `ChatResponse` y se registra en la base de datos.
6. Las cabeceras `X-Aquelarre-Provider` y `X-Aquelarre-Mode` indican el enrutamiento.

## Proveedores

| Provedor | Variable de entorno | Requiere clave | Cadena por defecto |
|---|---|---|---|
| Groq | `GROQ_API_KEY` | Sí | CODE, GENERAL |
| Gemini | `GEMINI_API_KEY` | Sí | REASONING, LONG_CONTEXT, GENERAL |
| OpenCode | `OPENCODE_BASE_URL` | No | CODE, REASONING, LONG_CONTEXT |
| Ollama | `OLLAMA_BASE_URL` | No | CODE, REASONING, LONG_CONTEXT |
| Kilo | `KILO_BASE_URL` | No | CODE, REASONING, GENERAL |

## Cuotas y circuit breakers

Cada proveedor tiene:
- Un token bucket con capacidad configurable (60 por defecto).
- Un circuit breaker que se abre después de 3 fallos consecutivos.
- Un cooldown de 300 segundos antes de reintentar.