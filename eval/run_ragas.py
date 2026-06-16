"""RAGAS evaluation harness for the RAG pipeline.

Runs the dataset in ``eval/dataset.json`` against a *running* stack, scoring the
retrieval + cited-generation quality. The harness talks to the backend over HTTP
only (no backend imports), so it can run from its own virtualenv:

For every question it:

1. Streams ``POST /chat`` (Server-Sent Events) and collects the full answer text
   and the terminal ``citations`` payload, reusing the same SSE framing the
   frontend reads (``data: <json>\\n\\n`` frames; ``delta`` events then a final
   ``citations`` event).
2. Builds ``contexts`` from the cited chunks: it fetches each cited
   ``chunk_id`` via ``GET /chunks/{id}`` and uses the chunk ``content``.
3. Scores the run with RAGAS — ``faithfulness``, ``answer_relevancy``,
   ``context_precision``, ``context_recall`` — using an OpenAI judge (the RAGAS
   default). ``OPENAI_API_KEY`` is read from the repo-root ``.env``.
4. Computes a custom ``citation_accuracy``: a citation is *valid* when its
   ``quote`` is a substring (whitespace-normalised) of the referenced chunk's
   ``content``. Reports the proportion of valid citations.

Outputs ``eval/results/report.json`` (per-question + aggregate scores) and
``eval/results/report.md`` (a readable summary that highlights the three worst
questions by faithfulness), and prints an aggregate summary to stdout.

Usage::

    python eval/run_ragas.py [--base-url URL] [--limit N] [--skip-ragas]

Configure the target with ``--base-url`` or ``RAG_API_BASE_URL`` (default
``http://localhost:8000``).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

EVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVAL_DIR.parent
DEFAULT_BASE_URL = "http://localhost:8000"
DATASET_PATH = EVAL_DIR / "dataset.json"
RESULTS_DIR = EVAL_DIR / "results"

# The refusal string the backend emits when the context does not cover the
# question. Dataset entries whose ground_truth equals this are "unanswerable"
# probes: we expect a refusal with no citations.
REFUSAL_ANSWER = "I don't have enough information to answer this question."

# RAGAS metrics we report, in display order.
RAGAS_METRICS = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]

# Columns that ``EvaluationResult.to_pandas()`` echoes back as inputs (everything
# else in the frame is a metric score column).
_INPUT_COLUMNS = {
    "user_input",
    "response",
    "retrieved_contexts",
    "reference",
    "reference_contexts",
    "question",
    "answer",
    "contexts",
    "ground_truth",
    "rubrics",
}

# Map RAGAS metric column names (which vary across versions) to our display names.
_METRIC_ALIASES = {
    "faithfulness": "faithfulness",
    "answer_relevancy": "answer_relevancy",
    "response_relevancy": "answer_relevancy",
    "context_precision": "context_precision",
    "llm_context_precision_with_reference": "context_precision",
    "context_recall": "context_recall",
}


# --------------------------------------------------------------------------- #
# HTTP / SSE helpers
# --------------------------------------------------------------------------- #
def _check_health(client: httpx.Client, base_url: str) -> None:
    """Fail fast with a clear message if the stack is not reachable."""
    try:
        response = client.get(f"{base_url}/health", timeout=10.0)
    except httpx.HTTPError as exc:
        raise SystemExit(
            f"ERROR: cannot reach the stack at {base_url} ({exc}).\n"
            f"Start it first: docker-compose -f infra/docker-compose.yml up --build"
        ) from exc
    # 503 means a dependency is degraded but the API is up; that is enough to try.
    if response.status_code not in (200, 503):
        raise SystemExit(f"ERROR: {base_url}/health returned {response.status_code}")


def _stream_chat(client: httpx.Client, base_url: str, question: str) -> tuple[str, list[dict[str, Any]]]:
    """POST /chat and read the SSE stream, returning ``(answer, citations)``."""
    answer_parts: list[str] = []
    citations: list[dict[str, Any]] = []

    def handle_frame(frame: str) -> None:
        data = "\n".join(
            line[len("data:") :].lstrip()
            for line in frame.splitlines()
            if line.startswith("data:")
        )
        if not data:
            return
        event = json.loads(data)
        if event.get("type") == "delta":
            answer_parts.append(event.get("text", ""))
        elif event.get("type") == "citations":
            citations.clear()
            citations.extend(event.get("citations", []))

    with client.stream(
        "POST",
        f"{base_url}/chat",
        json={"question": question, "conversation_id": None},
        timeout=180.0,
    ) as response:
        if response.status_code != 200:
            response.read()
            raise RuntimeError(
                f"POST /chat returned {response.status_code}: {response.text[:200]}"
            )
        buffer = ""
        for text in response.iter_text():
            buffer += text
            while "\n\n" in buffer:
                frame, buffer = buffer.split("\n\n", 1)
                handle_frame(frame)
        if buffer.strip():
            handle_frame(buffer)

    return "".join(answer_parts), citations


def _fetch_chunk_content(client: httpx.Client, base_url: str, chunk_id: str) -> str | None:
    """GET /chunks/{id}, returning the chunk ``content`` (or None if missing)."""
    response = client.get(f"{base_url}/chunks/{chunk_id}", timeout=30.0)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json().get("content", "")


# --------------------------------------------------------------------------- #
# Custom metric: citation accuracy
# --------------------------------------------------------------------------- #
def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _quote_is_grounded(quote: str, content: str | None) -> bool:
    """True when ``quote`` is a (whitespace-normalised) substring of ``content``."""
    if not quote or not content:
        return False
    return _normalize_ws(quote) in _normalize_ws(content)


# --------------------------------------------------------------------------- #
# Per-question collection
# --------------------------------------------------------------------------- #
def _collect_question(
    client: httpx.Client,
    base_url: str,
    entry: dict[str, Any],
    chunk_cache: dict[str, str | None],
) -> dict[str, Any]:
    """Run one question through the pipeline and gather everything we score."""
    question = entry["question"]
    ground_truth = entry["ground_truth"]
    unanswerable = _normalize_ws(ground_truth) == _normalize_ws(REFUSAL_ANSWER)

    answer, citations = _stream_chat(client, base_url, question)

    # Build contexts from the cited chunks (dedup, order-preserving) and validate
    # each citation's quote against the referenced chunk's content.
    contexts: "OrderedDict[str, str]" = OrderedDict()
    validated_citations: list[dict[str, Any]] = []
    valid_count = 0
    for citation in citations:
        chunk_id = str(citation.get("chunk_id"))
        if chunk_id not in chunk_cache:
            chunk_cache[chunk_id] = _fetch_chunk_content(client, base_url, chunk_id)
        content = chunk_cache[chunk_id]
        if content:
            contexts.setdefault(chunk_id, content)
        is_valid = _quote_is_grounded(citation.get("quote", ""), content)
        valid_count += int(is_valid)
        validated_citations.append(
            {
                "number": citation.get("number"),
                "chunk_id": chunk_id,
                "quote": citation.get("quote"),
                "document_name": citation.get("document_name"),
                "valid": is_valid,
            }
        )

    num_citations = len(citations)
    citation_accuracy = (valid_count / num_citations) if num_citations else None

    return {
        "question": question,
        "ground_truth": ground_truth,
        "expected_chunk_ids": entry.get("expected_chunk_ids", []),
        "unanswerable": unanswerable,
        "answer": answer,
        "contexts": list(contexts.values()),
        "citations": validated_citations,
        "num_citations": num_citations,
        "num_valid_citations": valid_count,
        "citation_accuracy": citation_accuracy,
    }


# --------------------------------------------------------------------------- #
# RAGAS scoring
# --------------------------------------------------------------------------- #
def _to_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if number != number else number  # filter NaN


def _run_ragas(records: list[dict[str, Any]], judge_model: str) -> list[dict[str, float | None]]:
    """Score each record with RAGAS, returning a per-record metric dict.

    Raises on import/setup errors so the caller can degrade gracefully (report
    the citation metric alone and note that RAGAS did not run).
    """
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings
    from ragas import EvaluationDataset, evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import (
        answer_relevancy,
        context_precision,
        context_recall,
        faithfulness,
    )

    samples = [
        {
            "user_input": record["question"],
            "response": record["answer"],
            "retrieved_contexts": record["contexts"],
            "reference": record["ground_truth"],
        }
        for record in records
    ]
    dataset = EvaluationDataset.from_list(samples)

    evaluator_llm = LangchainLLMWrapper(ChatOpenAI(model=judge_model, temperature=0.0))
    evaluator_embeddings = LangchainEmbeddingsWrapper(
        OpenAIEmbeddings(model="text-embedding-3-small")
    )

    result = evaluate(
        dataset=dataset,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        llm=evaluator_llm,
        embeddings=evaluator_embeddings,
        raise_exceptions=False,
    )

    frame = result.to_pandas()
    metric_columns = [c for c in frame.columns if c not in _INPUT_COLUMNS]

    per_record: list[dict[str, float | None]] = []
    for position in range(len(records)):
        scores: dict[str, float | None] = {name: None for name in RAGAS_METRICS}
        if position < len(frame):
            row = frame.iloc[position]
            for column in metric_columns:
                display = _METRIC_ALIASES.get(column, column)
                if display in scores:
                    scores[display] = _to_float(row[column])
        per_record.append(scores)
    return per_record


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def _mean(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return sum(present) / len(present) if present else None


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _build_aggregate(records: list[dict[str, Any]]) -> dict[str, float | None]:
    aggregate: dict[str, float | None] = {}
    for metric in RAGAS_METRICS:
        aggregate[metric] = _mean([r["scores"].get(metric) for r in records])
    # Mean of per-question citation accuracy (questions with no citations excluded).
    aggregate["citation_accuracy"] = _mean([r["citation_accuracy"] for r in records])
    # Citation accuracy pooled over every citation (valid / total).
    total = sum(r["num_citations"] for r in records)
    valid = sum(r["num_valid_citations"] for r in records)
    aggregate["citation_accuracy_overall"] = (valid / total) if total else None
    return aggregate


def _worst_by_faithfulness(records: list[dict[str, Any]], n: int = 3) -> list[dict[str, Any]]:
    scored = [r for r in records if r["scores"].get("faithfulness") is not None]
    scored.sort(key=lambda r: r["scores"]["faithfulness"])
    return scored[:n]


def _write_json_report(path: Path, metadata: dict[str, Any], aggregate: dict[str, Any], records: list[dict[str, Any]]) -> None:
    per_question = []
    for record in records:
        per_question.append(
            {
                "question": record["question"],
                "ground_truth": record["ground_truth"],
                "expected_chunk_ids": record["expected_chunk_ids"],
                "unanswerable": record["unanswerable"],
                "answer": record["answer"],
                "num_citations": record["num_citations"],
                "num_valid_citations": record["num_valid_citations"],
                "citation_accuracy": record["citation_accuracy"],
                "scores": record["scores"],
                "citations": record["citations"],
                "contexts": record["contexts"],
            }
        )
    payload = {"metadata": metadata, "aggregate": aggregate, "per_question": per_question}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_markdown_report(path: Path, metadata: dict[str, Any], aggregate: dict[str, Any], records: list[dict[str, Any]]) -> None:
    lines: list[str] = []
    lines.append("# RAGAS evaluation report")
    lines.append("")
    lines.append(f"- Generated: `{metadata['generated_at']}`")
    lines.append(f"- Target: `{metadata['api_base_url']}`")
    lines.append(f"- Questions: {metadata['num_questions']}")
    lines.append(f"- Judge model: `{metadata['judge_model']}`")
    if not metadata["ragas_ran"]:
        lines.append("")
        lines.append(f"> ⚠️ RAGAS metrics were not computed: {metadata['ragas_note']}")
    lines.append("")

    lines.append("## Aggregate scores")
    lines.append("")
    lines.append("| Metric | Score |")
    lines.append("| --- | --- |")
    for metric in RAGAS_METRICS:
        lines.append(f"| {metric} | {_fmt(aggregate.get(metric))} |")
    lines.append(f"| citation_accuracy (mean per question) | {_fmt(aggregate.get('citation_accuracy'))} |")
    lines.append(f"| citation_accuracy (pooled over citations) | {_fmt(aggregate.get('citation_accuracy_overall'))} |")
    lines.append("")

    lines.append("## Per-question scores")
    lines.append("")
    lines.append("| # | Question | faith. | ans.rel. | ctx.prec. | ctx.rec. | cite.acc. | #cites |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for index, record in enumerate(records, start=1):
        scores = record["scores"]
        question = record["question"].replace("|", "\\|")
        if len(question) > 70:
            question = question[:67] + "..."
        lines.append(
            "| {idx} | {q} | {f} | {ar} | {cp} | {cr} | {ca} | {nc} |".format(
                idx=index,
                q=question,
                f=_fmt(scores.get("faithfulness")),
                ar=_fmt(scores.get("answer_relevancy")),
                cp=_fmt(scores.get("context_precision")),
                cr=_fmt(scores.get("context_recall")),
                ca=_fmt(record["citation_accuracy"]),
                nc=record["num_citations"],
            )
        )
    lines.append("")

    worst = _worst_by_faithfulness(records, n=3)
    lines.append("## Three worst questions by faithfulness")
    lines.append("")
    if not worst:
        lines.append("_No faithfulness scores were available to rank._")
    for record in worst:
        lines.append(f"### {_fmt(record['scores'].get('faithfulness'))} — {record['question']}")
        lines.append("")
        lines.append(f"- **Ground truth:** {record['ground_truth']}")
        lines.append(f"- **Answer:** {record['answer']}")
        lines.append(
            f"- **Citations:** {record['num_valid_citations']}/{record['num_citations']} valid"
        )
        lines.append("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the RAGAS evaluation against a running stack.")
    parser.add_argument("--base-url", default=None, help=f"Backend base URL (default {DEFAULT_BASE_URL}).")
    parser.add_argument("--dataset", default=str(DATASET_PATH), help="Path to dataset.json.")
    parser.add_argument("--output-dir", default=str(RESULTS_DIR), help="Where to write report.{json,md}.")
    parser.add_argument("--limit", type=int, default=None, help="Only evaluate the first N questions.")
    parser.add_argument("--judge-model", default="gpt-4o-mini", help="OpenAI model for the RAGAS judge.")
    parser.add_argument("--skip-ragas", action="store_true", help="Skip RAGAS; only collect answers + citation accuracy.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    load_dotenv(REPO_ROOT / ".env")  # OPENAI_API_KEY / ANTHROPIC_API_KEY from the repo-root .env

    base_url = (args.base_url or os.environ.get("RAG_API_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")

    dataset = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    questions = dataset["questions"]
    if args.limit is not None:
        questions = questions[: args.limit]

    run_ragas = not args.skip_ragas
    ragas_note = ""
    if run_ragas and not os.environ.get("OPENAI_API_KEY"):
        run_ragas = False
        ragas_note = "OPENAI_API_KEY is not set (required for the RAGAS judge)."
        print(f"WARNING: {ragas_note} Continuing with citation_accuracy only.", file=sys.stderr)

    # 1. Collect answers + citations + contexts for every question.
    chunk_cache: dict[str, str | None] = {}
    records: list[dict[str, Any]] = []
    with httpx.Client() as client:
        _check_health(client, base_url)
        for index, entry in enumerate(questions, start=1):
            print(f"[{index}/{len(questions)}] {entry['question']}")
            record = _collect_question(client, base_url, entry, chunk_cache)
            record["scores"] = {name: None for name in RAGAS_METRICS}
            records.append(record)

    # 2. Score with RAGAS (best-effort: degrade to citation metric on failure).
    if run_ragas:
        print("\nScoring with RAGAS (this calls the OpenAI judge)...")
        try:
            per_record_scores = _run_ragas(records, args.judge_model)
            for record, scores in zip(records, per_record_scores):
                record["scores"] = scores
        except Exception as exc:  # noqa: BLE001 - report and continue
            run_ragas = False
            ragas_note = f"RAGAS failed: {exc}"
            print(f"WARNING: {ragas_note}", file=sys.stderr)

    # 3. Aggregate + report.
    aggregate = _build_aggregate(records)
    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "api_base_url": base_url,
        "num_questions": len(records),
        "judge_model": args.judge_model,
        "ragas_ran": run_ragas,
        "ragas_note": ragas_note,
        "metrics": RAGAS_METRICS + ["citation_accuracy"],
    }

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json_report(output_dir / "report.json", metadata, aggregate, records)
    _write_markdown_report(output_dir / "report.md", metadata, aggregate, records)

    # 4. Stdout summary.
    print("\n=== Aggregate scores ===")
    for metric in RAGAS_METRICS:
        print(f"  {metric:<22} {_fmt(aggregate.get(metric))}")
    print(f"  {'citation_accuracy':<22} {_fmt(aggregate.get('citation_accuracy'))}")
    print(f"  {'citation_accuracy (pooled)':<22} {_fmt(aggregate.get('citation_accuracy_overall'))}")
    if not run_ragas:
        print(f"\n  note: {ragas_note}")
    print(f"\nReports written to {output_dir / 'report.json'} and {output_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
