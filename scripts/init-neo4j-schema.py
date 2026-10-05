"""Apply the checked-in Neo4j constraints using the configured Neo4j driver."""

import os
from pathlib import Path

from neo4j import GraphDatabase


def main() -> None:
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD")
    if not password:
        raise SystemExit("NEO4J_PASSWORD must be set before initializing Neo4j.")

    schema_path = (
        Path(__file__).resolve().parents[1] / "docker" / "neo4j" / "001-ontology.cypher"
    )
    statements = [
        statement.strip()
        for statement in schema_path.read_text(encoding="utf-8").split(";")
        if statement.strip()
    ]
    with GraphDatabase.driver(uri, auth=(user, password)) as driver:
        driver.verify_connectivity()
        with driver.session() as session:
            for statement in statements:
                session.run(statement).consume()


if __name__ == "__main__":
    main()
