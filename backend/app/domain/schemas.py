"""OpenAI-compatible request and response schemas.

The wire format mirrors the OpenAI Chat Completions contract so the VS Code extension never has
to translate anything.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

MessageRole = Literal["system", "user", "assistant"]


class ChatMessage(BaseModel):
    """One turn of the conversation.

    Attributes:
        role: Who is speaking.
        content: Plain text of the turn.
    """

    role: MessageRole
    content: str


class ChatRequest(BaseModel):
    """Body accepted by `POST /v1/chat/completions`.

    Attributes:
        model: Provider to force, or `null` to let the router decide.
        messages: Conversation so far, oldest first.
        temperature: Sampling temperature forwarded to the provider.
        max_tokens: Upper bound on generated tokens.
        stream: Whether the client asked for streaming, which the MVP does not implement.
    """

    model: str | None = None
    messages: list[ChatMessage]
    temperature: float | None = 0.7
    max_tokens: int | None = None
    stream: bool = False

    def to_llm_messages(self) -> list[dict[str, str]]:
        """Return the conversation as the plain dictionaries LiteLLM consumes."""
        return [{"role": message.role, "content": message.content} for message in self.messages]


class RouteInfo(BaseModel):
    """Routing metadata attached to every successful response.

    Attributes:
        provider: Provider that actually answered.
        task_type: Task class the router detected.
        mode: `auto` when the router chose, `manual` when the client forced a provider.
        reason: Short technical explanation of the choice.
    """

    provider: str
    task_type: str
    mode: str
    reason: str


class ChatResponse(BaseModel):
    """Successful completion body, OpenAI-shaped plus Aquelarre routing metadata.

    Attributes:
        id: Completion identifier.
        object: Literal OpenAI object name.
        created: Unix timestamp of the completion.
        model: Model string reported by the provider.
        choices: OpenAI choice list returned upstream.
        usage: Token accounting returned upstream.
        aquelarre: Which provider answered and why.
    """

    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[dict[str, Any]]
    usage: dict[str, Any]
    aquelarre: RouteInfo
