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

"""Database permissions enforce the same decisions as the validator layer."""

from __future__ import annotations

import psycopg
import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def agent_connection(
    agent_rw_url: str,
) -> psycopg.Connection:
    connection = psycopg.connect(agent_rw_url)
    yield connection
    connection.close()


class TestColumnLevelPermissionsBlockSensitiveReads:
    def test_password_hash_is_unreachable(
        self, agent_connection: psycopg.Connection
    ) -> None:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with agent_connection.cursor() as cursor:
                cursor.execute("SELECT password_hash FROM users WHERE id = 1")

    def test_api_key_is_unreachable(self, agent_connection: psycopg.Connection) -> None:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with agent_connection.cursor() as cursor:
                cursor.execute("SELECT api_key FROM users WHERE id = 1")

    def test_select_star_fails_because_some_columns_are_forbidden(
        self, agent_connection: psycopg.Connection
    ) -> None:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with agent_connection.cursor() as cursor:
                cursor.execute("SELECT * FROM users WHERE id = 1")

    def test_permitted_columns_are_readable(
        self, agent_connection: psycopg.Connection
    ) -> None:
        with agent_connection.cursor() as cursor:
            cursor.execute("SELECT id, email, name FROM users WHERE id = 1")
            rows = cursor.fetchall()
        assert len(rows) == 1


class TestRoleCannotAlterSchema:
    @pytest.mark.parametrize(
        "ddl",
        [
            "DROP TABLE users",
            "ALTER TABLE users ADD COLUMN extra TEXT",
            "CREATE TABLE spawned (id INT)",
            "TRUNCATE orders",
        ],
    )
    def test_ddl_is_rejected_by_postgres(
        self, agent_connection: psycopg.Connection, ddl: str
    ) -> None:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with agent_connection.cursor() as cursor:
                cursor.execute(ddl)


class TestDangerousFunctionsAreRevoked:
    def test_pg_read_file_is_not_executable(
        self, agent_connection: psycopg.Connection
    ) -> None:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with agent_connection.cursor() as cursor:
                cursor.execute("SELECT pg_read_file('/etc/passwd')")


class TestReservedWordColumnsWork:
    @pytest.mark.parametrize(
        "column_name",
        ["user", "group"],
    )
    def test_quoted_reserved_word_column_in_users_is_readable(
        self, agent_connection: psycopg.Connection, column_name: str
    ) -> None:
        with agent_connection.cursor() as cursor:
            cursor.execute(f'SELECT "{column_name}" FROM users LIMIT 1')
            cursor.fetchall()

    @pytest.mark.parametrize(
        "column_name",
        ["order", "type", "analyse"],
    )
    def test_quoted_reserved_word_column_in_orders_is_readable(
        self, agent_connection: psycopg.Connection, column_name: str
    ) -> None:
        with agent_connection.cursor() as cursor:
            cursor.execute(f'SELECT "{column_name}" FROM orders LIMIT 1')
            cursor.fetchall()


class TestBoundedWritesWork:
    def test_insert_and_update_users_roundtrip(
        self, agent_connection: psycopg.Connection
    ) -> None:
        with agent_connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO users (email, name, password_hash) "
                "VALUES (%s, %s, %s) RETURNING id",
                ("roundtrip-test@example.com", "Roundtrip Test", "$2b$12$hash"),
            )
            row = cursor.fetchone()
            assert row is not None
            inserted_id = row[0]

            cursor.execute(
                "UPDATE users SET name = %s WHERE id = %s",
                ("Roundtrip Test Updated", inserted_id),
            )
            agent_connection.commit()

            cursor.execute("SELECT name FROM users WHERE id = %s", (inserted_id,))
            (fetched_name,) = cursor.fetchone()  # type: ignore[misc]
        assert fetched_name == "Roundtrip Test Updated"

    def test_insert_update_delete_roundtrip_on_orders(
        self, agent_connection: psycopg.Connection
    ) -> None:
        with agent_connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO orders (user_id, status, amount) "
                "VALUES (%s, %s, %s) RETURNING id",
                (1, "pending", 9.99),
            )
            row = cursor.fetchone()
            assert row is not None
            inserted_id = row[0]

            cursor.execute(
                "UPDATE orders SET status = %s WHERE id = %s",
                ("shipped", inserted_id),
            )
            cursor.execute("DELETE FROM orders WHERE id = %s", (inserted_id,))
            agent_connection.commit()

            cursor.execute("SELECT id FROM orders WHERE id = %s", (inserted_id,))
            assert cursor.fetchone() is None
