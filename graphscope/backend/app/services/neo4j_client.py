from __future__ import annotations

from functools import lru_cache

from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError

from app.core.config import get_settings


class Neo4jClient:
    def __init__(self, uri: str, user: str, password: str, database: str | None = None):
        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self._database = database

    def close(self) -> None:
        self._driver.close()

    def verify(self) -> bool:
        try:
            self._driver.verify_connectivity()
            return True
        except Neo4jError:
            return False

    def run_query(self, query: str, parameters: dict | None = None) -> list[dict]:
        parameters = parameters or {}
        with self._driver.session(database=self._database) as session:
            result = session.run(query, parameters)
            return [record.data() for record in result]


@lru_cache(maxsize=1)
def get_neo4j_client() -> Neo4jClient:
    settings = get_settings()
    return Neo4jClient(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
        database=settings.neo4j_database,
    )
