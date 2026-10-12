"""Linnet's baseline answer path: the 'before' picture.

The provider SDK runs with its defaults, so the SDK, not
Wrenholt's code, decides when to retry. Chapter 4 replaces this
path with the book's gateway, which sets max_retries=0 and owns
every retry.
"""

from openai import OpenAI

SYSTEM_PROMPT = (
    "You are Linnet, the customer-support assistant for "
    "Wrenholt Goods. Answer briefly and politely."
)


def make_client(base_url: str, api_key: str) -> OpenAI:
    """Baseline client: SDK defaults, including its retries."""
    return OpenAI(base_url=base_url, api_key=api_key)


def answer(client: OpenAI, model: str, question: str) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
    )
    return response.choices[0].message.content or ""
