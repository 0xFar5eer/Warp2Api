from __future__ import annotations

from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str
    content: Optional[Union[str, List[Dict[str, Any]]]] = ""
    tool_call_id: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    name: Optional[str] = None


class OpenAIFunctionDef(BaseModel):
    name: str
    description: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None


class OpenAITool(BaseModel):
    type: str = Field("function", description="Only 'function' is supported")
    function: OpenAIFunctionDef


class ChatCompletionsRequest(BaseModel):
    model: Optional[str] = None
    messages: List[ChatMessage]
    stream: Optional[bool] = False
    tools: Optional[List[OpenAITool]] = None
    tool_choice: Optional[Any] = None


# Embeddings models for KiloCode indexing support
class EmbeddingsRequest(BaseModel):
    input: Union[str, List[str]]  # Text(s) to embed
    model: str = "claude-4.1-opus"  # Default to claude-4.1-opus
    encoding_format: Optional[str] = "float"  # "float" or "base64"
    dimensions: Optional[int] = 1536  # Output dimensionality
    user: Optional[str] = None  # Optional user identifier


class EmbeddingData(BaseModel):
    object: str = "embedding"
    embedding: List[float]  # The embedding vector
    index: int  # Position in the input array


class EmbeddingsResponse(BaseModel):
    object: str = "list"
    data: List[EmbeddingData]
    model: str
    usage: Dict[str, int]  # Token usage information