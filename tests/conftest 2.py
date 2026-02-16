"""
Test fixtures for CoreSense backend tests.
Provides mock Supabase client and FastAPI test client.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from httpx import AsyncClient, ASGITransport


class MockSupabaseResponse:
    """Mock Supabase query response."""
    def __init__(self, data=None):
        self.data = data or []


class MockSupabaseQuery:
    """Chainable mock for Supabase query builder."""
    def __init__(self, data=None):
        self._data = data or []

    def select(self, *args, **kwargs):
        return self

    def insert(self, *args, **kwargs):
        return self

    def update(self, *args, **kwargs):
        return self

    def upsert(self, *args, **kwargs):
        return self

    def delete(self, *args, **kwargs):
        return self

    def eq(self, *args, **kwargs):
        return self

    def neq(self, *args, **kwargs):
        return self

    def gte(self, *args, **kwargs):
        return self

    def lte(self, *args, **kwargs):
        return self

    def lt(self, *args, **kwargs):
        return self

    def gt(self, *args, **kwargs):
        return self

    def order(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def range(self, *args, **kwargs):
        return self

    def in_(self, *args, **kwargs):
        return self

    def execute(self):
        return MockSupabaseResponse(self._data)

    def set_data(self, data):
        """Set the data that will be returned by execute()."""
        self._data = data
        return self


class MockSupabaseClient:
    """Mock Supabase client with configurable table responses."""
    def __init__(self):
        self._table_data = {}
        self.auth = MagicMock()

    def table(self, name):
        data = self._table_data.get(name, [])
        return MockSupabaseQuery(data)

    def set_table_data(self, table_name, data):
        """Configure what data a table query returns."""
        self._table_data[table_name] = data


@pytest.fixture
def mock_supabase():
    """Provide a configurable mock Supabase client."""
    return MockSupabaseClient()


@pytest.fixture
def mock_user_id():
    """Standard test user ID."""
    return "test-user-123"


@pytest.fixture
async def client(mock_supabase, mock_user_id):
    """FastAPI test client with mocked Supabase and auth."""
    with patch(
        'backend.database.supabase_client.get_supabase_client',
        return_value=mock_supabase
    ), patch(
        'backend.middleware.auth_helper.get_supabase_client',
        return_value=mock_supabase
    ), patch(
        'backend.routers.app_api.get_supabase_client',
        return_value=mock_supabase
    ), patch(
        'backend.middleware.auth_helper.get_current_user_id',
        return_value=mock_user_id
    ):
        # Configure mock auth to return a valid user
        mock_user = MagicMock()
        mock_user.user = MagicMock()
        mock_user.user.id = mock_user_id
        mock_supabase.auth.get_user.return_value = mock_user

        from backend.main import app
        from backend.middleware.auth_helper import get_current_user_id

        # Override the auth dependency
        app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

        app.dependency_overrides.clear()
