from neo4j import AsyncDriver, AsyncGraphDatabase
from neo4j.exceptions import Neo4jError

from app.core.config import Settings


class Neo4jConfigurationError(RuntimeError):
    pass


class Neo4jConnectionError(RuntimeError):
    pass


class Neo4jClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.neo4j_password:
            raise Neo4jConfigurationError(
                "NEO4J_PASSWORD must be configured to connect to Neo4j."
            )
        if not settings.neo4j_uri.startswith(("bolt://", "neo4j://")):
            raise Neo4jConfigurationError(
                "NEO4J_URI must use the Bolt protocol (bolt:// or neo4j://)."
            )

        self.database = settings.neo4j_database
        self.driver: AsyncDriver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )

    async def verify_connectivity(self) -> None:
        try:
            await self.driver.verify_connectivity()
        except Neo4jError as error:
            raise Neo4jConnectionError(
                "Could not connect to Neo4j using the configured Bolt endpoint."
            ) from error

    async def close(self) -> None:
        await self.driver.close()
