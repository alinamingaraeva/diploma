from pydantic import BaseModel, Field, model_validator
from typing import List, Optional, Literal, Dict, Any
from enum import Enum

class Role(str, Enum):
    user = "user"
    assistant = "assistant"
    system = "system"

class Message(BaseModel):
    role: Role
    content: str

class ChatRequest(BaseModel):
    messages: List[Message]
    model: Optional[str] = None
    temperature: float = Field(1.0, ge=0, le=2)
    max_tokens: int = Field(1000, ge=1, le=16000)
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    stream: bool = False

    @model_validator(mode='after')
    def validate_messages(self):
        if not self.messages:
            raise ValueError("At least one message required")
        return self

class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class ChatResponse(BaseModel):
    content: str
    model: str
    usage: Usage
    finish_reason: Optional[str] = None
    cached: bool = False

    @classmethod
    def from_openai(cls, openai_response, model: str, cached: bool = False):
        """Конвертирует ответ OpenAI в нашу схему"""
        choice = openai_response.choices[0]
        return cls(
            content=choice.message.content,
            model=model,
            usage=Usage(**openai_response.usage.model_dump()),
            finish_reason=choice.finish_reason,
            cached=cached
        )

class ChatDelta(BaseModel):
    """Для стриминга: либо текст, либо usage"""
    content: Optional[str] = None
    usage: Optional[Usage] = None