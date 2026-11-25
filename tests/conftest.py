import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.model import Fixture
from evaluation.support import isolated_schema


@pytest.fixture(scope="session")
def client():
    with isolated_schema(), TestClient(create_app(Fixture())) as client:
        yield client
