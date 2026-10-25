# Guía de despliegue

Este documento describe cómo desplegar Aquelarre en diferentes entornos.

## Docker

### Construir la imagen

```bash
cd backend
docker build -t aquelarre:latest .
```

### Ejecutar con Docker Compose

```bash
# Copiar .env.example a .env y completar los valores
cp .env.example .env

# Levantar los servicios
docker compose up -d

# Ver los logs
docker compose logs -f
```

### Ejecutar directamente

```bash
docker run -p 8000:8000 --env-file .env aquelarre:latest
```

## Entorno local

### Desarrollo

```bash
cd backend
uv run uvicorn main:app --reload
```

### Producción (sin Docker)

```bash
cd backend
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

## Variables de entorno

| Variable | Requerido | Descripción |
|---|---|---|
| `AQUELARRE_API_KEY` | Sí | Clave de API para autenticar las requests |
| `GROQ_API_KEY` | No | Clave de API de Groq |
| `GEMINI_API_KEY` | No | Clave de API de Gemini |
| `OLLAMA_BASE_URL` | No | URL base de Ollama (default: http://host.docker.internal:11434) |
| `OPENCODE_BASE_URL` | No | URL base de OpenCode |
| `KILO_BASE_URL` | No | URL base de Kilo |
| `DATABASE_URL` | No | URL de la base de datos (default: sqlite:///./data/aquelarre.db) |
| `LOG_LEVEL` | No | Nivel de logging (default: INFO) |
| `COOLDOWN_SECONDS` | No | Segundos de cooldown del circuit breaker (default: 300) |

## Health check

El endpoint `GET /health` no requiere autenticación y reporta el estado de cada proveedor:

```json
{
  "status": "ok",
  "providers": {
    "ollama-coder": {
      "tokens": 60.0,
      "capacity": 60,
      "failure_count": 0,
      "cooldown_seconds": 300.0,
      "circuit_open": false,
      "available": true
    }
  }
}
```