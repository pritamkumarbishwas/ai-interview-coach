"""Test-suite bootstrap: environment + an ephemeral MongoDB, before app imports.

Imported first by ``tests/conftest.py`` so these side effects happen before any
``app.*`` module is imported and reads its settings.

Tests must never touch the cluster named in ``backend/.env`` (it may be a shared
or production Atlas deployment, and it is often unreachable from CI anyway).
Unless the developer points the suite at a real server with ``TEST_MONGO_URI``,
we boot an ephemeral, managed ``mongod`` (downloaded once and cached by
``pymongo-inmemory``) and hand its connection string to the app. This keeps the
suite self-contained and exercises real GridFS, which an in-memory mock cannot.
"""

import os

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("MONGO_DB_NAME", "test_ai_interview_coach")
os.environ.setdefault("JWT_SECRET", "test-secret-do-not-use-in-production")
os.environ.setdefault("JWT_EXPIRES_MINUTES", "60")
os.environ.setdefault("LOG_LEVEL", "WARNING")
# Tests always use an embedded in-process Qdrant — never a server (and the
# backend/.env value may point at a cloud instance). Forced, not setdefault.
os.environ["QDRANT_URL"] = ":memory:"

MONGO_SERVER = None
if not os.environ.get("TEST_MONGO_URI"):
    from pymongo_inmemory import MongoClient as _InMemoryMongoClient

    MONGO_SERVER = _InMemoryMongoClient()
    _mongo_host, _mongo_port = MONGO_SERVER.address
    os.environ["MONGO_URI"] = f"mongodb://{_mongo_host}:{_mongo_port}"
