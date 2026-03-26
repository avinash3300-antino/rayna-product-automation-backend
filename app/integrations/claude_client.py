import anthropic

from app.core.config import settings


class ClaudeClient:
    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    async def generate(
        self,
        prompt: str,
        system: str = "",
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> str:
        messages = [{"role": "user", "content": prompt}]
        kwargs: dict = dict(model=model, max_tokens=max_tokens, messages=messages, temperature=temperature)
        if system:
            kwargs["system"] = system
        response = await self.client.messages.create(**kwargs)
        return response.content[0].text


claude_client = ClaudeClient()
