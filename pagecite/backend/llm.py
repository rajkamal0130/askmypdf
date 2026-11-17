"""Step 2: answer a question with OpenAI, grounded in chunks fetched from FAISS."""
from functools import lru_cache

import openai

from backend.config import LLM_MODEL

SYSTEM_PROMPT = """You answer questions using only the PDF excerpts provided in <documents>.

- Base every statement on the excerpts. If they don't contain the answer, say you couldn't find it in the uploaded PDFs; don't fill gaps from general knowledge.
- After each fact, cite its source as [file, p. N] using the file and page attributes of the excerpt.
- Be concise and direct. Use bullet points or a short table when it helps readability."""


@lru_cache(maxsize=1)
def get_client() -> openai.OpenAI:
    # Reads OPENAI_API_KEY from the environment
    return openai.OpenAI()


def _format_context(chunks: list[dict]) -> str:
    parts = [
        f'<excerpt file="{c["source"]}" page="{c["page"]}">\n{c["text"]}\n</excerpt>'
        for c in chunks
    ]
    return "<documents>\n" + "\n\n".join(parts) + "\n</documents>"


def answer(question: str, chunks: list[dict]) -> str:
    if not chunks:
        return "No relevant content found. Add PDFs to the `pdfs/` folder and sync first."

    response = get_client().chat.completions.create(
        model=LLM_MODEL,
        max_completion_tokens=16000,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"{_format_context(chunks)}\n\nQuestion: {question}"},
        ],
    )

    choice = response.choices[0]
    if choice.message.refusal:
        return "The model declined to answer this question."

    text = (choice.message.content or "").strip()
    if choice.finish_reason == "length":
        text += "\n\n_(answer truncated)_"
    return text
