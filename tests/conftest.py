import os
import pytest
from psycopg_pool import ConnectionPool

from feed_warrior.store import Store

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://feed_warrior:feed_warrior@localhost:5433/feed_warrior")

@pytest.fixture(scope="session")
def db_pool():
    pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=4, open=True)
    Store(pool).migrate("migrations")
    yield pool
    pool.close()

@pytest.fixture(autouse=True)
def clean_db(request):
    if "integration" not in request.node.nodeid:
        return
    pool = request.getfixturevalue("db_pool")
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE tweets, voice_samples, accounts, digests, digest_items, errors RESTART IDENTITY CASCADE")
        conn.commit()
