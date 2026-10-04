"""RAG: knowledge loading, retrieval filtering/fallbacks, prompt integration."""

import asyncio
import json
from uuid import uuid4

import pytest

from app.core.config import settings
from app.schemas.rag import KnowledgeChunk
from app.services.knowledge_loader import (
    MAX_CHUNK_CHARS,
    load_knowledge_base,
    parse_json,
    parse_markdown,
)
from app.services.rag_service import rag_service
from tests.conftest import Env


@pytest.fixture(autouse=True)
def clean_store():
    """The embedded `:memory:` store persists per process — isolate tests."""
    rag_service.delete_collections()
    yield
    rag_service.delete_collections()


def make_chunk(
    text: str, topic: str = "*", roles: list[str] | None = None, source: str = "test.md"
) -> KnowledgeChunk:
    return KnowledgeChunk(
        id=str(uuid4()),
        text=text,
        topic=topic,
        roles=roles if roles is not None else ["*"],
        source=source,
    )


# --- knowledge_loader -------------------------------------------------------


def test_markdown_is_chunked_tagged_and_has_stable_ids():
    text = (
        "---\n"
        "topic: row-level security\n"
        "roles: backend, data\n"
        "---\n"
        "\n"
        "Intro paragraph about policies.\n"
        "\n"
        "## Section two\n"
        "\n"
        "More details about enforcement.\n"
    )
    parsed = parse_markdown(text, "technical_concepts/rls.md")
    assert list(parsed) == ["technical_concepts"]
    chunks = parsed["technical_concepts"]
    assert chunks
    assert all(chunk.topic == "row-level security" for chunk in chunks)
    assert all(chunk.roles == ["backend", "data"] for chunk in chunks)
    assert all(len(chunk.text) <= MAX_CHUNK_CHARS for chunk in chunks)
    assert any("Section two" in chunk.text for chunk in chunks)

    again = parse_markdown(text, "technical_concepts/rls.md")
    assert [c.id for c in chunks] == [c.id for c in again["technical_concepts"]]


def test_oversized_paragraph_is_hard_sliced_within_bound():
    body = "x" * (MAX_CHUNK_CHARS * 2 + 10)
    parsed = parse_markdown(f"---\ntopic: t\n---\n\n{body}", "technical_concepts/big.md")
    chunks = parsed["technical_concepts"]
    assert len(chunks) == 3
    assert all(len(chunk.text) <= MAX_CHUNK_CHARS for chunk in chunks)


def test_json_entries_group_by_collection(tmp_path):
    data = json.dumps(
        [
            {"text": "Alpha fact.", "topic": "t1"},
            {
                "text": "Beta fact.",
                "topic": "t2",
                "collection": "behavioral_questions",
                "roles": ["hr"],
            },
        ]
    )
    parsed = parse_json(data, "role_knowledge/bank.json")
    assert [c.text for c in parsed["role_knowledge"]] == ["Alpha fact."]
    assert [c.text for c in parsed["behavioral_questions"]] == ["Beta fact."]
    assert parsed["behavioral_questions"][0].roles == ["hr"]


def test_loader_groups_by_directory_and_rejects_stray_files(tmp_path):
    root = tmp_path / "kb"
    (root / "technical_concepts").mkdir(parents=True)
    (root / "technical_concepts" / "a.md").write_text("# Title\n\nContent.", encoding="utf-8")
    (root / "notes.txt").write_text("ignored", encoding="utf-8")

    grouped = load_knowledge_base(root)
    assert list(grouped) == ["technical_concepts"]
    assert grouped["technical_concepts"]

    stray_root = tmp_path / "stray_kb"
    stray_root.mkdir()
    (stray_root / "stray.md").write_text("No front matter.", encoding="utf-8")
    with pytest.raises(ValueError, match="not a collection"):
        load_knowledge_base(stray_root)
    with pytest.raises(FileNotFoundError):
        load_knowledge_base(tmp_path / "missing")


# --- retrieval --------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_then_retrieve_filters_by_topic_and_role():
    caching = make_chunk(
        "Caching strategies for read-heavy APIs.", topic="caching", roles=["backend"]
    )
    security = make_chunk(
        "Role based access control patterns.", topic="security", roles=["backend"]
    )
    frontend = make_chunk(
        "Frontend state management patterns.", topic="frontend", roles=["frontend"]
    )
    general = make_chunk("General interviewing advice.", topic="*", roles=["*"])
    devops = make_chunk("Queue based load leveling.", topic="caching", roles=["devops"])
    await rag_service.upsert("technical_concepts", [caching, security, frontend, general, devops])

    hits = await rag_service.retrieve_context(
        role="Backend Engineer",
        topic="caching",
        interview_type="technical",
        k=5,
    )
    assert hits
    hit_ids = {hit.id for hit in hits}
    # topic filter keeps caching + "*" chunks; role filter drops devops-only.
    assert hit_ids <= {caching.id, general.id}
    assert all(hit.topic in ("caching", "*") for hit in hits)


@pytest.mark.asyncio
async def test_topic_filter_falls_back_when_nothing_matches():
    chunks = [make_chunk(f"Kafka fact {n}.", topic="kafka") for n in range(4)]
    await rag_service.upsert("technical_concepts", chunks)

    hits = await rag_service.retrieve_context(
        role="any", topic="distributed tracing", interview_type="technical"
    )
    assert hits, "topic mismatch must fall back to an unfiltered search"
    assert all(hit.topic == "kafka" for hit in hits)


@pytest.mark.asyncio
async def test_role_filter_falls_back_when_it_would_starve():
    chunks = [make_chunk(f"Ops fact {n}.", roles=["devops"]) for n in range(3)]
    await rag_service.upsert("technical_concepts", chunks)

    hits = await rag_service.retrieve_context(
        role="Backend Engineer", topic="", interview_type="technical"
    )
    assert hits


@pytest.mark.asyncio
async def test_retrieve_respects_top_k_and_returns_empty_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
):
    await rag_service.upsert("technical_concepts", [make_chunk(f"Fact {n}.") for n in range(6)])
    hits = await rag_service.retrieve_context(role="", topic="", interview_type="technical", k=3)
    assert len(hits) == 3

    monkeypatch.setattr(settings, "rag_enabled", False)
    assert rag_service.enabled is False
    assert await rag_service.retrieve_context(role="", topic="", interview_type="technical") == []


@pytest.mark.asyncio
async def test_upsert_rejects_unknown_collection():
    with pytest.raises(ValueError, match="Unknown collection"):
        await rag_service.upsert("not_a_collection", [make_chunk("x")])


# --- prompt integration -----------------------------------------------------


def test_first_question_prompt_includes_retrieved_knowledge(env: Env):
    asyncio.run(
        rag_service.upsert(
            "technical_concepts",
            [make_chunk("The secret token is xylophone-42.", roles=["*"])],
        )
    )
    env.setup(target=1)
    prompt = env.prompts[-1]
    assert "<relevant_knowledge>" in prompt
    assert "xylophone-42" in prompt


def test_first_question_prompt_uses_placeholder_when_rag_disabled(
    env: Env, monkeypatch: pytest.MonkeyPatch
):
    asyncio.run(
        rag_service.upsert(
            "technical_concepts",
            [make_chunk("The secret token is xylophone-42.", roles=["*"])],
        )
    )
    monkeypatch.setattr(settings, "rag_enabled", False)
    env.setup(target=1)
    prompt = env.prompts[-1]
    assert "(knowledge base disabled)" in prompt
    assert "xylophone-42" not in prompt


def test_next_question_prompt_includes_retrieved_knowledge(env: Env, client, auth_headers: dict):
    asyncio.run(
        rag_service.upsert(
            "technical_concepts",
            [make_chunk("The secret token is xylophone-42.", roles=["*"])],
        )
    )
    session = env.setup(target=2)
    answered = client.post(
        f"/api/questions/{session['question_id']}/answer",
        headers=auth_headers,
        json={"answer": "I would profile first, then fix the bottleneck."},
    )
    assert answered.status_code == 200, answered.text

    prompt = env.prompts[-1]  # evaluation prompt precedes the next-question one
    assert "<relevant_knowledge>" in prompt
    assert "xylophone-42" in prompt


def test_rag_failure_degrades_but_question_is_still_generated(
    env: Env, monkeypatch: pytest.MonkeyPatch
):
    async def boom(*args, **kwargs):
        raise ConnectionError("qdrant unreachable")

    monkeypatch.setattr(rag_service, "retrieve_context", boom)
    session = env.setup(target=1)
    assert session["question_id"]
    assert "(knowledge base unavailable)" in env.prompts[-1]
