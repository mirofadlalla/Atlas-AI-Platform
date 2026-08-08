"""
generate_eval_dataset.py
------------------------
Fetches all document chunks from Qdrant for a given tenant_id,
then uses an LLM (HuggingFace) to auto-generate questions + answers
from each chunk, and saves the result as evaluation_dataset.json.

Usage:
    python -m app.rag.evaluation.generate_eval_dataset
"""

import json
import logging
from pathlib import Path

from qdrant_client import QdrantClient
from app.core.config import settings

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


QDRANT_URL = settings.qdrant_url
COLLECTION_NAME = settings.qdrant_collection_name
TENANT_ID = None  # change to your tenant
OUTPUT_PATH = Path(__file__).parent / "evaluation_dataset.json"
MAX_CHUNKS = 30  # how many chunks to generate questions from


def fetch_points(tenant_id: str, max_chunks: int = MAX_CHUNKS) -> list[dict]:
    """Scroll through Qdrant and return points belonging to tenant_id."""
    client = QdrantClient(url=QDRANT_URL)
    all_points = []
    offset = None

    global TENANT_ID
    TENANT_ID = tenant_id  # store for later use in main()

    logger.info(
        f"Fetching points for tenant_id='{tenant_id}' from '{COLLECTION_NAME}' ..."
    )

    while True:
        result, next_offset = client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter={
                "must": [{"key": "payload.tenant_id", "match": {"value": tenant_id}}]
            },
            limit=50,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )

        for point in result:
            all_points.append(
                {
                    "id": str(point.id),
                    "content": point.payload.get("content", ""),
                    "metadata": point.payload.get("payload", {}),
                }
            )

        logger.info(f"  Fetched {len(all_points)} points so far ...")

        if next_offset is None or len(all_points) >= max_chunks:
            break
        offset = next_offset

    # trim to max_chunks
    all_points = all_points[:max_chunks]
    logger.info(f"Total points to process: {len(all_points)}")
    return all_points


def build_llm():
    """Initialize the Groq LLM via CustomLocalLLM wrapper."""
    from app.services.llm_runner import CustomLocalLLM

    return CustomLocalLLM()


PROMPT_TEMPLATE = """\
You are an expert at creating evaluation datasets for RAG (Retrieval-Augmented Generation) systems.

Given the following document chunk, generate ONE factual question that can be answered DIRECTLY and ONLY from the text below.
Then provide the exact answer from the text.
Also provide 2 paraphrase variants of the question.

Document chunk:
\"\"\"
{content}
\"\"\"

Respond in this EXACT JSON format (no extra text):
{{
  "question": "<your question>",
  "answer": "<exact answer from the text>",
  "paraphrases": ["<variant 1>", "<variant 2>"]
}}
"""


def generate_qa(llm, content: str) -> dict | None:
    """Ask the LLM to generate a QA pair from a chunk. Returns None on failure."""
    prompt = PROMPT_TEMPLATE.format(content=content.strip())
    try:
        response = llm.invoke(prompt)
        raw = (
            response
            if isinstance(response, str)
            else getattr(response, "content", str(response))
        )
        raw = raw.strip()

        # Try to parse JSON — the LLM might wrap it in backticks
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        return json.loads(raw.strip())
    except Exception as e:
        logger.warning(f"  LLM generation failed: {e}")
        return None


def build_dataset(points: list[dict], llm) -> list[dict]:
    """For each point, generate a QA sample and attach the source chunk id."""
    dataset = []
    q_counter = 1

    for point in points:
        doc_id = point["id"]
        content = point["content"]

        if not content.strip():
            logger.warning(f"  Skipping empty chunk: {doc_id}")
            continue

        logger.info(f"  [{q_counter}] Generating QA for chunk {doc_id[:8]}...")
        qa = generate_qa(llm, content)

        if qa is None:
            logger.warning(
                f"  Skipping chunk {doc_id[:8]} — LLM returned no valid JSON."
            )
            continue

        dataset.append(
            {
                "id": f"q_{q_counter:03d}",
                "question": qa.get("question", ""),
                "answer": qa.get("answer", ""),
                "relevant_ids": [doc_id],
                "paraphrases": qa.get("paraphrases", []),
                # Optional: store the source chunk for traceability
                "_source_chunk": content[:300],
            }
        )
        q_counter += 1

    return dataset


def main():
    # 1. Fetch points from Qdrant
    points = fetch_points(tenant_id=TENANT_ID, max_chunks=MAX_CHUNKS)
    if not points:
        logger.error("No points found! Check your TENANT_ID and Qdrant connection.")
        return

    # 2. Build LLM
    logger.info("Initializing LLM ...")
    llm = build_llm()

    # 3. Generate QA dataset
    logger.info("Generating evaluation dataset ...")
    dataset = build_dataset(points, llm)

    if not dataset:
        logger.error("Dataset is empty — all LLM calls may have failed.")
        return

    # 4. Save to JSON
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2, ensure_ascii=False)

    logger.info(f"✅ Saved {len(dataset)} QA samples to: {OUTPUT_PATH}")
    print(json.dumps(dataset[:2], indent=2, ensure_ascii=False))  # preview first 2


if __name__ == "__main__":
    main()
