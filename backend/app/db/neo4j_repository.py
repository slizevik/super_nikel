import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any, Literal
from uuid import UUID

import structlog
from neo4j import AsyncDriver
from neo4j import AsyncManagedTransaction
from neo4j.exceptions import Neo4jError

from app.db.ontology import EntityType, RelationshipType
from app.schemas.extraction import ExtractionResult


logger = structlog.get_logger(__name__)

_ENTITY_LABELS = {entity_type: entity_type.value for entity_type in EntityType}
_RELATIONSHIP_TYPES = {
    relationship_type: relationship_type.value
    for relationship_type in RelationshipType
}


class Neo4jRepositoryError(RuntimeError):
    pass


TransactionCallback = Callable[[AsyncManagedTransaction], Awaitable[Any]]


class Neo4jRepository:
    def __init__(self, driver: AsyncDriver, database: str = "neo4j") -> None:
        self._driver = driver
        self._database = database

    async def upsert_extraction(
        self,
        document_id: UUID,
        extraction: ExtractionResult,
    ) -> None:
        """Idempotently persist one validated extraction and its provenance."""
        document_id_value = str(document_id)
        entities_by_id = {entity.id: entity for entity in extraction.entities}
        entities_by_type: dict[EntityType, list[dict[str, Any]]] = defaultdict(list)
        for entity in extraction.entities:
            if entity.type == EntityType.DOCUMENT:
                continue
            entities_by_type[entity.type].append(
                {
                    **entity.model_dump(mode="json"),
                    "source_document_id": document_id_value,
                }
            )
        persisted_entities_count = sum(map(len, entities_by_type.values()))

        async def write_transaction(transaction: AsyncManagedTransaction) -> None:
            await self._run(
                transaction,
                """
                MERGE (document:Document {document_id: $document_id})
                ON CREATE SET
                    document.name = $document_id,
                    document.source_document_id = $document_id,
                    document.source_documents = [$document_id]
                """,
                document_id=document_id_value,
            )

            for entity_type, entities in entities_by_type.items():
                label = _ENTITY_LABELS[entity_type]
                await self._run(
                    transaction,
                    f"""
                    UNWIND $entities AS entity
                    MERGE (node:`{label}` {{canonical_label: entity.canonical_label}})
                    ON CREATE SET
                        node.name = entity.canonical_label,
                        node.label = entity.label,
                        node.aliases = entity.aliases,
                        node.evidence = entity.evidence,
                        node.source_document_id = $document_id,
                        node.source_documents = [$document_id]
                    ON MATCH SET
                        node.aliases = reduce(
                            merged = coalesce(node.aliases, []),
                            alias IN entity.aliases |
                            CASE
                                WHEN alias IN merged THEN merged
                                ELSE merged + alias
                            END
                        ),
                        node.source_documents =
                            CASE
                                WHEN $document_id IN coalesce(node.source_documents, [])
                                THEN coalesce(node.source_documents, [])
                                ELSE coalesce(node.source_documents, []) + $document_id
                            END
                    WITH node, entity
                    MATCH (document:Document {{document_id: $document_id}})
                    MERGE (node)-[source:described_in
                        {{source_document_id: $document_id}}]->(document)
                    SET source.evidence = entity.evidence
                    """,
                    entities=entities,
                    document_id=document_id_value,
                )

            for relationship in extraction.relationships:
                source = entities_by_id[relationship.source_id]
                target = entities_by_id[relationship.target_id]
                source_pattern = self._endpoint_pattern("source", source.type)
                target_pattern = self._endpoint_pattern("target", target.type)
                relationship_type = _RELATIONSHIP_TYPES[relationship.type]
                await self._run(
                    transaction,
                    f"""
                    MATCH {source_pattern}
                    MATCH {target_pattern}
                    MERGE (source)-[relation:`{relationship_type}`
                        {{source_document_id: $document_id}}]->(target)
                    SET relation.evidence = $evidence
                    """,
                    document_id=document_id_value,
                    source_label=source.canonical_label,
                    target_label=target.canonical_label,
                    evidence=relationship.evidence,
                )

        await self._execute_transaction("write", write_transaction)
        logger.info(
            "neo4j_extraction_upserted",
            document_id=document_id_value,
            entities_count=persisted_entities_count,
            relationships_count=len(extraction.relationships),
        )

    async def get_entity(
        self,
        entity_type: EntityType,
        identifier: str,
    ) -> dict[str, Any] | None:
        label = _ENTITY_LABELS[entity_type]
        identity_property = (
            "document_id"
            if entity_type == EntityType.DOCUMENT
            else "canonical_label"
        )
        query = f"""
        MATCH (node:`{label}` {{{identity_property}: $identifier}})
        RETURN properties(node) AS entity
        """

        async def read_entity(
            transaction: AsyncManagedTransaction,
        ) -> list[dict[str, Any]]:
            return await self._read_records(
                transaction,
                query,
                identifier=identifier,
            )

        records = await self._execute_transaction(
            "read",
            read_entity,
        )
        return records[0]["entity"] if records else None

    async def get_entities_for_document(
        self,
        document_id: UUID,
    ) -> list[dict[str, Any]]:
        query = """
        MATCH (document:Document {document_id: $document_id})
        MATCH (entity)-[:described_in {source_document_id: $document_id}]->(document)
        RETURN labels(entity) AS labels, properties(entity) AS entity
        ORDER BY entity.name
        """

        async def read_entities(
            transaction: AsyncManagedTransaction,
        ) -> list[dict[str, Any]]:
            return await self._read_records(
                transaction,
                query,
                document_id=str(document_id),
            )

        records = await self._execute_transaction(
            "read",
            read_entities,
        )
        return records

    @staticmethod
    def _endpoint_pattern(
        variable: str,
        entity_type: EntityType,
    ) -> str:
        if entity_type == EntityType.DOCUMENT:
            return f"({variable}:Document {{document_id: $document_id}})"
        label = _ENTITY_LABELS[entity_type]
        return f"({variable}:`{label}` {{canonical_label: ${variable}_label}})"

    async def _execute_transaction(
        self,
        operation: Literal["read", "write"],
        callback: TransactionCallback,
    ) -> Any:
        started_at = time.perf_counter()
        try:
            async with self._driver.session(database=self._database) as session:
                if operation == "write":
                    await session.execute_write(callback)
                else:
                    return await session.execute_read(callback)
        except Neo4jError as error:
            logger.exception(
                "neo4j_operation_failed",
                operation=operation,
                error_type=type(error).__name__,
                execution_time_ms=round(
                    (time.perf_counter() - started_at) * 1000,
                    2,
                ),
            )
            raise Neo4jRepositoryError(
                f"Neo4j {operation} operation failed."
            ) from error
        else:
            logger.debug(
                "neo4j_operation_succeeded",
                operation=operation,
                execution_time_ms=round(
                    (time.perf_counter() - started_at) * 1000,
                    2,
                ),
            )

    async def _read_records(
        self,
        transaction: AsyncManagedTransaction,
        query: str,
        **parameters: Any,
    ) -> list[dict[str, Any]]:
        records = await self._run(transaction, query, **parameters)
        logger.debug(
            "neo4j_records_fetched",
            query_text=query,
            records_fetched=len(records),
        )
        return records

    async def _run(
        self,
        transaction: AsyncManagedTransaction,
        query: str,
        **parameters: Any,
    ) -> list[dict[str, Any]]:
        started_at = time.perf_counter()
        result = await transaction.run(query, parameters)
        records = [dict(record) async for record in result]
        await result.consume()
        logger.debug(
            "neo4j_query_completed",
            query_text=query,
            execution_time_ms=round((time.perf_counter() - started_at) * 1000, 2),
            records_fetched=len(records),
        )
        return records
