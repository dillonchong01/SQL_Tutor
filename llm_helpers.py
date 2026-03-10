"""LangChain-powered helpers for structured and free-form LLM generation."""

import json
import logging
import os

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

LOGGER = logging.getLogger(__name__)


class LLMClient:
    """Thin async wrapper around LangChain ChatOpenAI."""

    def __init__(self, model=None):
        model_name = model or os.getenv("OPENAI_MODEL", "gpt-4.1")
        self.client = ChatOpenAI(model=model_name, api_key=os.getenv("OPENAI_API_KEY"), temperature=0.2)

    async def generate_json(self, system_prompt, user_prompt):
        """Request strict JSON from the model and parse it."""
        response = await self.client.ainvoke(
            [
                SystemMessage(content=system_prompt + " Return only valid JSON."),
                HumanMessage(content=user_prompt),
            ]
        )
        raw = response.content
        if isinstance(raw, list):
            raw = "".join([str(item) for item in raw])
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            LOGGER.exception("Invalid JSON from model: %s", raw)
            raise ValueError("Model did not return valid JSON") from exc

    async def generate_text(self, system_prompt, user_prompt):
        response = await self.client.ainvoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
        )
        return str(response.content)
