# Guía de contribución

Este documento describe cómo contribuir al proyecto Aquelarre.

## Pre-requisitos

- Python 3.11+
- uv (gestor de paquetes)
- Docker (opcional, para despliegue)

## Configuración inicial

```bash
# Clonar el repositorio
git clone https://github.com/tu-org/aquelarre.git
cd aquelarre

# Copiar el archivo de configuración
cp .env.example .env
# Editar .env con tus valores

# Instalar dependencias
cd backend
uv sync

# Inicializar la base de datos (opcional, se crea automáticamente al arrancar)
python -c "from app.infrastructure import db; db.init_db('sqlite:///./data/aquelarre.db')"
```

## Ejecución local

```bash
# Desarrollo con recarga automática
uv run uvicorn main:app --reload

# Producción
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

## Testing

```bash
# Ejecutar todos los tests
uv run pytest -v

# Ejecutar con cobertura
uv run pytest --cov=app --cov-report=term-missing

# Ejecutar un test específico
uv run pytest tests/test_router.py::test_classify_detects_code_block -v
```

## Linting

```bash
# Verificar estilo de código
uv run ruff check .

# Auto-corregir errores comunes
uv run ruff check . --fix
``

## Commits

Usamos Conventional Commits. El asunto debe estar en inglés, imperativo, minúscula, sin punto final, máx. 72 caracteres. El cuerpo debe estar en español.

Ejemplos:
```
feat(router): add fallback chain for long context tasks

Se añade una cadena de fallback para tareas de largo contexto que use Gemini como primer proveedor.
```

```
fix(security): use hmac.compare_digest for key comparison

Se reemplaza la comparación directa de strings por hmac.compare_digest para evitar timing attacks.
```

## Estructura de branches

- `main` — Branch estable, solo para releases.
- `develop` — Branch de desarrollo integrado.
- `feature/*` — Nuevas funcionalidades.
- `fix/*` — Correcciones de bugs.
- `docs/*` — Documentación.

## Requisitos para merge

- Todas las pruebas deben pasar (`pytest -v`).
- El linter no debe reportar errores (`ruff check .`).
- Los commits deben seguir la convención de Conventional Commits.
- La documentación debe estar actualizada.