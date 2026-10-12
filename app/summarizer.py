"""Ollama-backed summarization service with map-reduce chunking for long documents."""
from __future__ import annotations

import os
from typing import Callable, Iterable

import requests

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")

# Approximate character budget per LLM call. Kept to ~24,000 characters
# (~6,000 tokens), optimal for llama3.2's 128k context and qwen3's 40k+ context.
CHUNK_CHARS = 24000
MAX_SECTIONS_PER_REDUCE = 12

SUMMARY_MODES: dict[str, dict[str, str]] = {
    "quick": {
        "label": "Quick Summary",
        "instruction": (
            "Write a concise summary in 1 short paragraph (80-120 words). "
            "Capture only the main idea and the single most important outcome."
        ),
    },
    "bullets": {
        "label": "Key Points",
        "instruction": (
            "Summarize as 5-8 bullet points. Each bullet must be a single, "
            "self-contained takeaway with the concrete fact, number, or name it "
            "depends on. Start every bullet with '- '. No preamble."
        ),
    },
    "detailed": {
        "label": "In-Depth Analysis",
        "instruction": (
            "Produce a structured analysis with these markdown sections:\n"
            "## Overview\n## Key Findings\n## Important Details\n## Conclusion\n"
            "Be thorough but avoid repetition. Keep every claim grounded in the source."
        ),
    },
}


class OllamaError(RuntimeError):
    """Raised when the local Ollama server cannot serve a request."""


def _generate(prompt: str, model: str, timeout: int = 300) -> str:
    """Send a single non-streaming generation request to Ollama."""
    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 1200},
            },
            timeout=timeout,
        )
    except requests.exceptions.ConnectionError as exc:
        raise OllamaError(
            "Could not reach Ollama at "
            f"{OLLAMA_URL}. Start it with 'ollama serve' and ensure the model "
            f"'{model}' is pulled with 'ollama pull {model}'."
        ) from exc
    except requests.exceptions.Timeout as exc:
        raise OllamaError("Ollama timed out while generating the summary.") from exc

    if response.status_code == 404:
        raise OllamaError(
            f"Model '{model}' is not installed. Run: ollama pull {model}"
        )
    if not response.ok:
        raise OllamaError(f"Ollama returned HTTP {response.status_code}: {response.text[:200]}")

    data = response.json()
    text = (data.get("response") or "").strip()
    if not text:
        raise OllamaError("Ollama returned an empty response.")
    return text


def chunk_text(text: str, size: int = CHUNK_CHARS) -> list[str]:
    """Split text into paragraph-aligned chunks of at most ~`size` characters."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current: list[str] = []
    length = 0

    for para in paragraphs:
        # A single oversized paragraph (rare) is hard-split.
        while len(para) > size:
            if current:
                chunks.append("\n\n".join(current))
                current, length = [], 0
            chunks.append(para[:size])
            para = para[size:]

        if length + len(para) + 2 > size and current:
            chunks.append("\n\n".join(current))
            current, length = [], 0

        current.append(para)
        length += len(para) + 2

    if current:
        chunks.append("\n\n".join(current))
    return chunks or [text]


def _build_single_pass_prompt(text: str, mode: str, filename: str) -> str:
    spec = SUMMARY_MODES[mode]
    return (
        "You are a precise document analyst. Summarize the document below.\n\n"
        f"Document: {filename}\n"
        f"Task: {spec['instruction']}\n\n"
        "Rules:\n"
        "- Use only information present in the document.\n"
        "- Do not invent facts, statistics, or citations.\n"
        "- Match the language of the document.\n"
        "- Output the summary only, with no meta commentary.\n\n"
        "----- DOCUMENT START -----\n"
        f"{text}\n"
        "----- DOCUMENT END -----"
    )


def _build_reduce_prompt(partials: Iterable[str], mode: str, filename: str) -> str:
    spec = SUMMARY_MODES[mode]
    joined = "\n\n".join(
        f"--- Section {i + 1} ---\n{part}" for i, part in enumerate(partials)
    )
    return (
        "You are a precise document analyst. Below are sequential section summaries "
        "of one larger document, in order.\n\n"
        f"Document: {filename}\n"
        f"Task: {spec['instruction']}\n\n"
        "Rules:\n"
        "- Synthesize the sections into one unified summary of the whole document.\n"
        "- Do not repeat section markers; write for a reader who never saw them.\n"
        "- Use only information present in the sections.\n"
        "- Match the language of the document.\n"
        "- Output the summary only, with no meta commentary.\n\n"
        "----- SECTIONS START -----\n"
        f"{joined}\n"
        "----- SECTIONS END -----"
    )


def summarize(
    text: str,
    mode: str = "detailed",
    filename: str = "document.pdf",
    model: str = DEFAULT_MODEL,
    on_progress: Callable[[str], None] | None = None,
) -> dict:
    """Summarize `text` using Ollama. Long inputs use map-reduce chunking.

    Returns a dict with the summary text plus metadata about how it was produced.
    """
    if mode not in SUMMARY_MODES:
        raise ValueError(f"Unknown summary mode '{mode}'.")

    def progress(message: str) -> None:
        if on_progress:
            on_progress(message)

    chunks = chunk_text(text)

    if len(chunks) == 1:
        progress("Analyzing document with the local model...")
        summary = _generate(_build_single_pass_prompt(text, mode, filename), model)
        return {
            "summary": summary,
            "mode": mode,
            "model": model,
            "chunks": 1,
            "strategy": "single-pass",
            "characters": len(text),
        }

    partials: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        progress(f"Summarizing section {index} of {len(chunks)}...")
        partials.append(
            _generate(
                "Summarize the following section of a larger document in 4-6 dense "
                "sentences, preserving concrete facts, names, and numbers. Match the "
                "document's language. Output the summary only.\n\n"
                f"----- SECTION START -----\n{chunk}\n----- SECTION END -----",
                model,
            )
        )

    # Hierarchical map-reduce: if many sections (100-200 pages), collapse in groups
    while len(partials) > MAX_SECTIONS_PER_REDUCE:
        progress(f"Condensing {len(partials)} sections into higher-level summaries...")
        next_level = []
        for i in range(0, len(partials), MAX_SECTIONS_PER_REDUCE):
            batch = partials[i : i + MAX_SECTIONS_PER_REDUCE]
            batch_text = "\n\n".join(f"Part {j+1}: {p}" for j, p in enumerate(batch))
            condensed = _generate(
                "Combine the following section summaries into one cohesive summary "
                "preserving the key facts, findings, and structure:\n\n"
                f"{batch_text}",
                model,
            )
            next_level.append(condensed)
        partials = next_level

    progress("Combining section summaries into the final result...")
    summary = _generate(_build_reduce_prompt(partials, mode, filename), model)
    return {
        "summary": summary,
        "mode": mode,
        "model": model,
        "chunks": len(chunks),
        "strategy": "hierarchical-map-reduce" if len(chunks) > MAX_SECTIONS_PER_REDUCE else "map-reduce",
        "characters": len(text),
    }


def health() -> dict:
    """Report whether Ollama is reachable and which models are installed."""
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        response.raise_for_status()
        models = [m.get("name", "") for m in response.json().get("models", [])]
    except Exception as exc:  # noqa: BLE001
        return {
            "ollama": False,
            "url": OLLAMA_URL,
            "default_model": DEFAULT_MODEL,
            "models": [],
            "error": str(exc),
        }

    return {
        "ollama": True,
        "url": OLLAMA_URL,
        "default_model": DEFAULT_MODEL,
        "model_ready": any(m.split(":")[0] == DEFAULT_MODEL.split(":")[0] for m in models),
        "models": models,
    }