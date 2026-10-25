# Aquelarre — Normas del proyecto

Documento normativo obligatorio para cualquier agente o persona que escriba código en este repositorio.
El incumplimiento de una norma de este documento es un error de revisión, no una preferencia.

---

## 1. Idiomas

| Superficie | Idioma |
|---|---|
| Código, identificadores, docstrings, comentarios técnicos, mensajes de commit | Inglés |
| `README.md` y `docs/` | Español |
| Texto visible en pantalla (errores de API, respuestas al usuario) | Bilingüe: `{"es": "...", "en": "..."}` |
| Este documento | Español, con tokens de código en inglés |

---

## 2. Estructura de carpetas

Organización **por capa** (By Type / clean architecture). Un módulo vive en la capa cuya responsabilidad
asume, nunca en la que lo necesite por conveniencia.

```
backend/app/
├── api/              # Transporte HTTP: rutas, manejo de errores HTTP. Sin lógica de negocio.
├── core/             # Transversal: configuración, logging, seguridad. Depende solo de libs externas.
├── domain/           # Lógica pura: router, cuotas, esquemas. Sin red, sin disco, sin I/O.
├── infrastructure/   # Adaptadores externos: base de datos, cliente LiteLLM.
└── main.py           # Composición: factory de la app, CORS, startup. Nada más.
```

Reglas de dependencia:

- `domain/` **nunca** importa de `api/`, `infrastructure/` ni `main.py`.
- `api/` importa de `domain/` y `core/`, jamás de `infrastructure/` directamente.
- `main.py` solo compone e inyecta; no contiene lógica de negocio.
- Un archivo = una responsabilidad. Si un módulo acumula dos, se parte.

Nombres de módulos en `snake_case`, uno por concepto. Nunca `utils.py`, `helpers.py` ni `misc.py`:
si no tiene responsabilidad propia, no tiene archivo.

---

## 3. Naming

| Elemento | Convención | Ejemplo |
|---|---|---|
| Clases, dataclasses, enums | `PascalCase` | `HybridRouter`, `ProviderState` |
| Métodos y funciones | `snake_case` | `pick_available()`, `classify_task()` |
| Variables y parámetros | `snake_case` | `failure_count`, `requested_model` |
| Constantes y enums members | `UPPER_SNAKE` | `COOLDOWN_SECONDS`, `TaskType.CODE` |
| Módulos y paquetes | `snake_case` | `litellm_client.py` |
| Rutas de API | `kebab-case` en URL | `/v1/chat/completions` |

Los nombres revelan intención: `pick_available`, no `get_one`; `record_failure`, no `bad()`.

---

## 4. Comentarios

**Prohibido comentar el *qué* hace el código.** Si el código necesita esa línea, el nombre está mal.

Sólo se documenta el *porqué*:

```python
# LiteLLM appends /chat/completions itself, so api_base must end in /v1.
LITELLM_API_SUFFIX = ""
```

Prohibido:

- Bloques de cabecera de archivo con autor o fecha.
- Comentarios de sección (`# --- imports ---`).
- Código comentado. El historial de git existe para eso.
- Comentarios obvios (`# loop over providers` sobre un `for provider in providers`).
- Docstrings que repiten la firma.

Docstrings en **inglés**, formato **Google**, sólo en clases y funciones públicas.
`__init__`, propiedades internas y helpers privados no llevan docstring si el nombre basta.

---

## 5. Clean code y SRP

- **Single Responsibility**: una función hace una cosa y la hace completa. Si el nombre lleva `and`
  o `or`, se parte.
- Funciones cortas: máximo ~40 líneas, un solo nivel de abstracción por función.
- Sin `else` anidado más de un nivel; se usa guard clause temprana (`return`/`raise` al inicio).
- Sin parámetros booleanos de flag: son dos funciones o una enumeración.
- Nada de código especulativo: no se escribe código para un caso que aún no existe.
- Sin duplicación de lógica de decisión: si dos lugares deciden lo mismo, la decisión sube a `core/`
  o baja a `domain/`.
- Los valores mágicos viven en `core/config.py` o en constantes con nombre, nunca inline.

---

## 6. Tipado y documentación

- **Type hints en el 100 % de las firmas públicas**, incluido el retorno (`-> None`, `-> dict[str, int]`).
- `Any` sólo en payloads de LLM, y justificado en el punto donde se usa.
- Sin imports circulares. Si aparece uno, la frontera de capa está mal dibujada.

---

## 7. Prohibiciones duras

| Prohibido | Alternativa obligatoria |
|---|---|
| `print()` | `logging` configurado en `core/logging_setup.py` |
| `except:` o `except Exception:` sin motivo claro | Capturar la excepción concreta |
| `os.getenv` fuera de `core/config.py` | `pydantic-settings` |
| `time.sleep()` en handlers async | `asyncio.sleep()` |
| Secretos en código, tests o logs | `sanitize_for_logs()` + variables de entorno |
| `allow_origins=["*"]` | Orígenes explícitos |
| Lógica de negocio en `main.py` | Moverla a `domain/` o `core/` |
| Llamadas de red en `domain/` | `infrastructure/` |
| Features no pedidas (streaming real, RAG, etc.) | El MVP es el MVP |

---

## 8. Seguridad

- Claves **sólo** en `.env`, que está en `.gitignore`. Nunca en el repositorio.
- `/v1/*` exige `Authorization: Bearer <AQUELARRE_API_KEY>` sin excepciones.
- Comparación de claves con `hmac.compare_digest`, nunca `==`.
- Los mensajes al usuario son genéricos y bilingües; el detalle va al log interno.
- Todo log que pueda contener entrada del usuario o configuración pasa por `sanitize_for_logs()`.
- Docker corre como usuario no root.

---

## 9. Commits

Conventional Commits, configurados en `.cz.toml` (commitizen).

- **Asunto en inglés**, imperativo, minúscula, sin punto final, máx. 72 caracteres.
- **Cuerpo en español**, explicando el *porqué* del cambio.
- Un commit por unidad de responsabilidad completa y verde (`pytest` + `ruff` antes de commitear).
- Prefijos: `feat`, `fix`, `docs`, `chore`, `test`, `refactor`, `perf`, `ci`, `build`.
- Scope en inglés y minúscula: `feat(router): ...`, `feat(infrastructure): ...`.
- **Nunca** se hace `git push`. Lo hace el propietario del repositorio.

---

## 10. Tests

- `pytest` + `pytest-asyncio`, sin red externa: LiteLLM se mockea siempre.
- Los tests no dependen del orden en que se ejecuten.
- Sin claves reales en los tests: se usan valores de entorno de prueba en `conftest.py`.
- `pytest -v` debe terminar en menos de 5 segundos.
- `ruff check` a 0 errores antes de cada commit.

---

## 11. Dependencias y entorno

- Gestor de paquetes: **uv**. Comandos: `uv run pytest`, `uv run ruff check`.
- Python **3.11**.
- Toda configuración de entorno está centralizada en `core/config.py`. El YAML de LiteLLM usa
  `os.environ/...` y nunca literales.
