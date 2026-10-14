import asyncio
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.db.neo4j_client import Neo4jClient, Neo4jConfigurationError
from app.db.neo4j_repository import Neo4jRepository
from app.schemas.extraction import (
    EntityType,
    ExtractedEntity,
    ExtractedRelationship,
    ExtractionResult,
    RelationshipType,
)


class FakeResult:
    def __init__(self, records=None) -> None:
        self.records = records or []

    def __aiter__(self):
        self._iterator = iter(self.records)
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration:
            raise StopAsyncIteration from None

    async def consume(self):
        return None


class FakeTransaction:
    def __init__(self) -> None:
        self.queries: list[tuple[str, dict]] = []

    async def run(self, query, parameters):
        self.queries.append((query, parameters))
        if "RETURN properties(node) AS entity" in query:
            return FakeResult([{"entity": {"name": "Nickel leaching"}}])
        if "RETURN labels(entity) AS labels" in query:
            return FakeResult([{"labels": ["Process"], "entity": {"name": "Process"}}])
        return FakeResult()


class FakeSession:
    def __init__(self, transaction) -> None:
        self.transaction = transaction

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def execute_write(self, callback):
        return await callback(self.transaction)

    async def execute_read(self, callback):
        return await callback(self.transaction)


class FakeDriver:
    def __init__(self) -> None:
        self.transaction = FakeTransaction()
        self.databases: list[str] = []

    def session(self, database):
        self.databases.append(database)
        return FakeSession(self.transaction)


def make_extraction() -> ExtractionResult:
    text = "Nickel leaching uses nickel ore."
    return ExtractionResult(
        entities=[
            ExtractedEntity(
                id="process",
                type=EntityType.PROCESS,
                label="Nickel leaching",
                canonical_label="Nickel leaching",
                evidence=text,
            ),
            ExtractedEntity(
                id="material",
                type=EntityType.MATERIAL,
                label="nickel ore",
                canonical_label="nickel ore",
                evidence=text,
            ),
            ExtractedEntity(
                id="document",
                type=EntityType.DOCUMENT,
                label="Source article",
                canonical_label="Source article",
                evidence=text,
            ),
        ],
        relationships=[
            ExtractedRelationship(
                source_id="process",
                target_id="material",
                type=RelationshipType.USES_MATERIAL,
                evidence=text,
            ),
            ExtractedRelationship(
                source_id="process",
                target_id="document",
                type=RelationshipType.DESCRIBED_IN,
                evidence=text,
            ),
        ],
    )


def test_upsert_writes_document_entities_and_relationship_idempotently():
    driver = FakeDriver()
    repository = Neo4jRepository(driver, database="nikelpower")
    document_id = uuid4()

    asyncio.run(repository.upsert_extraction(document_id, make_extraction()))

    assert driver.databases == ["nikelpower"]
    assert len(driver.transaction.queries) == 5
    queries = [query for query, _ in driver.transaction.queries]
    assert "MERGE (document:Document" in queries[0]
    assert "MERGE (node:`Process`" in queries[1]
    assert "MERGE (node:`Material`" in queries[2]
    assert "MERGE (source)-[relation:`uses_material`" in queries[3]
    assert "MATCH (target:Document {document_id: $document_id})" in queries[4]
    assert "MERGE (source)-[relation:`described_in`" in queries[4]
    assert all("MERGE" in query for query in queries)
    assert all(
        str(document_id) == params.get("document_id")
        for _, params in driver.transaction.queries
    )
    assert "source_document_id" in queries[1]
    assert "described_in" in queries[1]


def test_repository_can_read_an_entity_and_entities_for_document():
    driver = FakeDriver()
    repository = Neo4jRepository(driver)
    document_id = uuid4()

    async def read():
        entity = await repository.get_entity(
            EntityType.PROCESS,
            "Nickel leaching",
        )
        document_entities = await repository.get_entities_for_document(document_id)
        return entity, document_entities

    entity, document_entities = asyncio.run(read())

    assert entity == {"name": "Nickel leaching"}
    assert document_entities == [
        {"labels": ["Process"], "entity": {"name": "Process"}}
    ]
    assert len(driver.transaction.queries) == 2
    assert driver.transaction.queries[0][1] == {
        "identifier": "Nickel leaching"
    }
    assert driver.transaction.queries[1][1] == {"document_id": str(document_id)}


def test_repository_reads_document_by_document_id():
    driver = FakeDriver()
    repository = Neo4jRepository(driver)
    document_id = str(uuid4())

    document = asyncio.run(
        repository.get_entity(EntityType.DOCUMENT, document_id)
    )

    assert document == {"name": "Nickel leaching"}
    query, parameters = driver.transaction.queries[0]
    assert "MATCH (node:`Document` {document_id: $identifier})" in query
    assert parameters == {"identifier": document_id}


def test_neo4j_client_requires_password():
    settings = Settings(
        database_url="postgresql+psycopg://localhost/nikelpower",
        neo4j_password=None,
    )

    with pytest.raises(Neo4jConfigurationError, match="NEO4J_PASSWORD"):
        Neo4jClient(settings)


def test_neo4j_client_rejects_non_bolt_uri():
    settings = Settings(
        database_url="postgresql+psycopg://localhost/nikelpower",
        neo4j_uri="http://localhost:7474",
        neo4j_password="test-password",
    )

    with pytest.raises(Neo4jConfigurationError, match="Bolt protocol"):
        Neo4jClient(settings)


def test_neo4j_client_verifies_connectivity_and_closes_driver(monkeypatch):
    calls = []

    class Driver:
        async def verify_connectivity(self):
            calls.append("verify")

        async def close(self):
            calls.append("close")

    monkeypatch.setattr(
        "app.db.neo4j_client.AsyncGraphDatabase.driver",
        lambda uri, auth: calls.append((uri, auth)) or Driver(),
    )
    settings = Settings(
        database_url="postgresql+psycopg://localhost/nikelpower",
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        neo4j_password="test-password",
    )
    client = Neo4jClient(settings)

    async def verify_and_close():
        await client.verify_connectivity()
        await client.close()

    asyncio.run(verify_and_close())

    assert calls == [
        ("bolt://localhost:7687", ("neo4j", "test-password")),
        "verify",
        "close",
    ]
