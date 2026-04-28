# MIT License
#
# Copyright (c) 2026 Philipp Höllinger
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

"""Shared fixtures for integration tests that spin up a real Postgres."""

from __future__ import annotations

import pathlib
from collections.abc import Iterator

import psycopg
import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
INIT_SQL_PATH = (
    REPO_ROOT / "src" / "infrastructure" / "persistence" / "postgres" / "init.sql"
)


def _docker_is_reachable() -> bool:
    try:
        import docker
    except ImportError:
        return False
    try:
        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def postgres_admin_url() -> Iterator[str]:
    """Starts a Postgres container and runs init.sql against it once."""
    if not _docker_is_reachable():
        pytest.skip("Docker daemon not reachable: integration tests skipped")

    from testcontainers.postgres import PostgresContainer

    container = PostgresContainer(
        image="postgres:16-alpine",
        username="postgres",
        password="postgres",
        dbname="demo",
    )
    container.start()
    try:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(5432)
        admin_url = f"postgresql://postgres:postgres@{host}:{port}/demo"
        sql_script = INIT_SQL_PATH.read_text(encoding="utf-8")
        with psycopg.connect(admin_url, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql_script)
        yield admin_url
    finally:
        container.stop()


@pytest.fixture(scope="session")
def agent_rw_url(postgres_admin_url: str) -> str:
    """The connection URL for the restricted agent role."""
    without_scheme = postgres_admin_url.split("://", 1)[1]
    _, host_and_rest = without_scheme.split("@", 1)
    return f"postgresql://agent_rw:agent_pw@{host_and_rest}"
