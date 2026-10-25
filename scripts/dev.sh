#!/usr/bin/env bash
# Development helper script for Aquelarre.
# Usage: ./scripts/dev.sh [command]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_ROOT/backend"

cd "$BACKEND_DIR"

case "${1:-help}" in
  install|setup)
    echo "Installing dependencies..."
    uv sync
    echo "Done. Copy .env.example to .env and edit it."
    ;;

  run|start)
    echo "Starting development server..."
    exec uv run uvicorn main:app --reload
    ;;

  test)
    echo "Running tests..."
    exec uv run pytest -v
    ;;

  lint)
    echo "Running linter..."
    exec uv run ruff check .
    ;;

  format)
    echo "Formatting code..."
    exec uv run ruff format .
    ;;

  fix)
    echo "Auto-fixing lint errors..."
    exec uv run ruff check . --fix
    ;;

  docker-build)
    echo "Building Docker image..."
    docker build -t aquelarre:latest .
    ;;

  docker-run)
    echo "Running Docker container..."
    docker run -p 8000:8000 --env-file "$PROJECT_ROOT/.env" aquelarre:latest
    ;;

  compose-up)
    echo "Starting services with Docker Compose..."
    docker compose up -d
    ;;

  compose-down)
    echo "Stopping services..."
    docker compose down
    ;;

  db-init)
    echo "Initializing database..."
    uv run python -c "from app.infrastructure import db; db.init_db('sqlite:///./data/aquelarre.db')"
    ;;

  help|*)
    echo "Aquelarre development script"
    echo ""
    echo "Usage: ./scripts/dev.sh [command]"
    echo ""
    echo "Commands:"
    echo "  install|setup   Install dependencies"
    echo "  run|start       Start development server"
    echo "  test            Run tests"
    echo "  lint            Run linter"
    echo "  format          Format code"
    echo "  fix             Auto-fix lint errors"
    echo "  docker-build    Build Docker image"
    echo "  docker-run      Run Docker container"
    echo "  compose-up      Start services with Docker Compose"
    echo "  compose-down    Stop services"
    echo "  db-init         Initialize database"
    echo "  help            Show this help"
    ;;
esac