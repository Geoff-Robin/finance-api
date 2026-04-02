"""
Comprehensive pytest suite validating Authentication, CRUD workflows,
user management, role-based access control, search, and rate limiting.
"""
import pytest
import pytest_asyncio
import os
from httpx import AsyncClient, ASGITransport
from datetime import date

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_api_cases.db"
os.environ["JWT_SECRET_KEY"] = "super-secret-test-key"

import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from main import app
from models import Base
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.asyncio

@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_db():
    """
    Session-scoped fixture bootstrapping the test database and mapping tables.
    Also handles cleanup of the temporary SQLite DB after tests conclude.
    """
    engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
    if os.path.exists("./test_api_cases.db"):
        os.remove("./test_api_cases.db")

@pytest_asyncio.fixture(scope="module")
async def client():
    """
    Module-scoped HTTP client fixture connecting directly to the ASGI app via httpx.
    Ensures standard FastAPI lifespan context initialization occurs.
    """
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testServer") as ac:
            yield ac



async def test_register_admin_successful(client: AsyncClient):
    """Admin registration returns 201 and an access token."""
    resp = await client.post(
        "/register",
        json={"email": "admin@example.com", "password": "pass", "role": "admin"},
    )
    assert resp.status_code == 201
    assert "access_token" in resp.json()


async def test_register_viewer_successful(client: AsyncClient):
    """Viewer registration returns 201."""
    resp = await client.post(
        "/register",
        json={"email": "viewer@example.com", "password": "pass", "role": "viewer"},
    )
    assert resp.status_code == 201


async def test_register_analyst_successful(client: AsyncClient):
    """Analyst registration returns 201."""
    resp = await client.post(
        "/register",
        json={"email": "analyst@example.com", "password": "pass", "role": "analyst"},
    )
    assert resp.status_code == 201


async def test_register_duplicate_email(client: AsyncClient):
    """Duplicate email registration returns 400."""
    resp = await client.post(
        "/register",
        json={"email": "admin@example.com", "password": "pass", "role": "admin"},
    )
    assert resp.status_code == 400


async def test_login_successful(client: AsyncClient):
    """Existing user login returns 200 and a token."""
    resp = await client.post(
        "/login", json={"email": "admin@example.com", "password": "pass"}
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


async def test_login_wrong_password(client: AsyncClient):
    """Wrong password returns 401."""
    resp = await client.post(
        "/login", json={"email": "admin@example.com", "password": "wrong"}
    )
    assert resp.status_code == 401


async def test_login_wrong_email(client: AsyncClient):
    """Unknown email returns 401."""
    resp = await client.post(
        "/login", json={"email": "nobody@example.com", "password": "pass"}
    )
    assert resp.status_code == 401


@pytest_asyncio.fixture(scope="module")
async def tokens(client: AsyncClient):
    """
    Cache JWT tokens for admin, analyst, and viewer across the test module.

    Args:
        client (AsyncClient): Client abstraction linking to the backend.

    Returns:
        dict: Mapping of role names to their active JWT strings.
    """
    admin_resp = await client.post(
        "/login", json={"email": "admin@example.com", "password": "pass"}
    )
    viewer_resp = await client.post(
        "/login", json={"email": "viewer@example.com", "password": "pass"}
    )
    analyst_resp = await client.post(
        "/login", json={"email": "analyst@example.com", "password": "pass"}
    )
    return {
        "admin": admin_resp.json()["access_token"],
        "viewer": viewer_resp.json()["access_token"],
        "analyst": analyst_resp.json()["access_token"],
    }

async def test_list_users_as_admin(client: AsyncClient, tokens: dict):
    """Admin can retrieve all users."""
    resp = await client.get(
        "/users/", headers={"Authorization": f"Bearer {tokens['admin']}"}
    )
    assert resp.status_code == 200
    assert len(resp.json()) >= 3


async def test_list_users_forbidden_for_viewer(client: AsyncClient, tokens: dict):
    """Viewer cannot list users — expects 403."""
    resp = await client.get(
        "/users/", headers={"Authorization": f"Bearer {tokens['viewer']}"}
    )
    assert resp.status_code == 403


async def test_list_users_forbidden_for_analyst(client: AsyncClient, tokens: dict):
    """Analyst cannot list users — expects 403."""
    resp = await client.get(
        "/users/", headers={"Authorization": f"Bearer {tokens['analyst']}"}
    )
    assert resp.status_code == 403


async def test_get_single_user_as_admin(client: AsyncClient, tokens: dict):
    """Admin can retrieve a specific user by ID."""
    resp = await client.get(
        "/users/1", headers={"Authorization": f"Bearer {tokens['admin']}"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "email" in data
    assert "role" in data
    assert "is_active" in data


async def test_get_nonexistent_user(client: AsyncClient, tokens: dict):
    """Fetching a non-existent user ID returns 404."""
    resp = await client.get(
        "/users/9999", headers={"Authorization": f"Bearer {tokens['admin']}"}
    )
    assert resp.status_code == 404


async def test_update_user_role_as_admin(client: AsyncClient, tokens: dict):
    """Admin can reassign a user's role."""
    users_resp = await client.get(
        "/users/", headers={"Authorization": f"Bearer {tokens['admin']}"}
    )
    viewer = next(u for u in users_resp.json() if u["email"] == "viewer@example.com")

    resp = await client.patch(
        f"/users/{viewer['id']}",
        json={"role": "analyst"},
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "analyst"
    await client.patch(
        f"/users/{viewer['id']}",
        json={"role": "viewer"},
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )


async def test_deactivate_user_as_admin(client: AsyncClient, tokens: dict):
    """Admin can deactivate a non-admin user account."""
    users_resp = await client.get(
        "/users/", headers={"Authorization": f"Bearer {tokens['admin']}"}
    )
    analyst = next(u for u in users_resp.json() if u["email"] == "analyst@example.com")

    resp = await client.patch(
        f"/users/{analyst['id']}",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


async def test_inactive_user_cannot_login(client: AsyncClient):
    """A deactivated user is blocked from logging in (403)."""
    resp = await client.post(
        "/login", json={"email": "analyst@example.com", "password": "pass"}
    )
    assert resp.status_code == 403
    assert "inactive" in resp.json()["detail"].lower()


async def test_inactive_user_token_rejected(client: AsyncClient, tokens: dict):
    """An existing JWT for a deactivated account is rejected (403)."""
    resp = await client.get(
        "/financial-records/",
        headers={"Authorization": f"Bearer {tokens['analyst']}"},
    )
    assert resp.status_code == 403


async def test_reactivate_user_as_admin(client: AsyncClient, tokens: dict):
    """Admin can reactivate a previously deactivated account."""
    users_resp = await client.get(
        "/users/", headers={"Authorization": f"Bearer {tokens['admin']}"}
    )
    analyst = next(u for u in users_resp.json() if u["email"] == "analyst@example.com")

    resp = await client.patch(
        f"/users/{analyst['id']}",
        json={"is_active": True},
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is True


async def test_admin_cannot_deactivate_themselves(client: AsyncClient, tokens: dict):
    """An admin cannot deactivate their own account — expects 400."""
    users_resp = await client.get(
        "/users/", headers={"Authorization": f"Bearer {tokens['admin']}"}
    )
    admin = next(u for u in users_resp.json() if u["email"] == "admin@example.com")

    resp = await client.patch(
        f"/users/{admin['id']}",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )
    assert resp.status_code == 400


async def test_create_valid_record(client: AsyncClient, tokens: dict):
    """Admin can create a financial record and gets 201."""
    data = {
        "amount": 1500.00,
        "type": "income",
        "category": "Salary",
        "date": str(date.today()),
        "notes": "Test salary",
    }
    resp = await client.post(
        "/financial-records/",
        json=data,
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )
    assert resp.status_code == 201
    assert resp.json()["amount"] == "1500.00"


async def test_create_restricted_for_viewer(client: AsyncClient, tokens: dict):
    """Viewer cannot create records — expects 403."""
    data = {
        "amount": 50.00,
        "type": "expense",
        "category": "Food",
        "date": str(date.today()),
    }
    resp = await client.post(
        "/financial-records/",
        json=data,
        headers={"Authorization": f"Bearer {tokens['viewer']}"},
    )
    assert resp.status_code == 403


async def test_create_restricted_for_analyst(client: AsyncClient, tokens: dict):
    """Analyst cannot create records — expects 403."""
    data = {
        "amount": 50.00,
        "type": "expense",
        "category": "Food",
        "date": str(date.today()),
    }
    resp = await client.post(
        "/financial-records/",
        json=data,
        headers={"Authorization": f"Bearer {tokens['analyst']}"},
    )
    assert resp.status_code == 403


async def test_create_invalid_data(client: AsyncClient, tokens: dict):
    """Negative amount fails schema validation — expects 422."""
    data = {
        "amount": -100.00,
        "type": "expense",
        "category": "Food",
        "date": str(date.today()),
    }
    resp = await client.post(
        "/financial-records/",
        json=data,
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )
    assert resp.status_code == 422


async def test_list_records_as_analyst(client: AsyncClient, tokens: dict):
    """Analyst can list records."""
    resp = await client.get(
        "/financial-records/",
        headers={"Authorization": f"Bearer {tokens['analyst']}"},
    )
    assert resp.status_code == 200


async def test_list_records_restricted_for_viewer(client: AsyncClient, tokens: dict):
    """Viewer cannot list records — expects 403."""
    resp = await client.get(
        "/financial-records/",
        headers={"Authorization": f"Bearer {tokens['viewer']}"},
    )
    assert resp.status_code == 403


async def test_list_records_filtered(client: AsyncClient, tokens: dict):
    """Filtering by type=expense returns only matching records."""
    resp = await client.get(
        "/financial-records/?type=expense",
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 0  # no expense created successfully yet


async def test_get_single_record_as_analyst(client: AsyncClient, tokens: dict):
    """Analyst can fetch a specific record by ID."""
    resp = await client.get(
        "/financial-records/1",
        headers={"Authorization": f"Bearer {tokens['analyst']}"},
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == 1


async def test_get_single_record_restricted_for_viewer(
    client: AsyncClient, tokens: dict
):
    """Viewer cannot fetch individual records — expects 403."""
    resp = await client.get(
        "/financial-records/1",
        headers={"Authorization": f"Bearer {tokens['viewer']}"},
    )
    assert resp.status_code == 403


async def test_update_record(client: AsyncClient, tokens: dict):
    """Admin can update a record amount."""
    resp = await client.patch(
        "/financial-records/1",
        json={"amount": 1600.00},
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )
    assert resp.status_code == 200
    assert resp.json()["amount"] == "1600.00"


async def test_update_restricted_for_viewer(client: AsyncClient, tokens: dict):
    """Viewer cannot update records — expects 403."""
    resp = await client.patch(
        "/financial-records/1",
        json={"amount": 1700.00},
        headers={"Authorization": f"Bearer {tokens['viewer']}"},
    )
    assert resp.status_code == 403


# ── 4. Dashboard Summary ───────────────────────────────────────────


async def test_get_dashboard_summary_as_viewer(client: AsyncClient, tokens: dict):
    """Viewer can access the dashboard summary."""
    # Add an expense first so summary is meaningful
    await client.post(
        "/financial-records/",
        json={
            "amount": 600.00,
            "type": "expense",
            "category": "Rent",
            "date": str(date.today()),
        },
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )
    resp = await client.get(
        "/financial-records/summary",
        headers={"Authorization": f"Bearer {tokens['viewer']}"},
    )
    assert resp.status_code == 200
    summary = resp.json()
    assert "total_income" in summary
    assert "total_expenses" in summary
    assert "net_balance" in summary


async def test_get_dashboard_summary_as_analyst(client: AsyncClient, tokens: dict):
    """Analyst can access the dashboard summary."""
    resp = await client.get(
        "/financial-records/summary",
        headers={"Authorization": f"Bearer {tokens['analyst']}"},
    )
    assert resp.status_code == 200


async def test_summary_values_correct(client: AsyncClient, tokens: dict):
    """Dashboard totals are calculated correctly after known insertions."""
    resp = await client.get(
        "/financial-records/summary",
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )
    assert resp.status_code == 200
    summary = resp.json()
    assert summary["total_income"] == "1600.00"
    assert summary["total_expenses"] == "600.00"
    assert summary["net_balance"] == "1000.00"


# ── 5. Soft Delete & Visibility ────────────────────────────────────


async def test_soft_delete_record(client: AsyncClient, tokens: dict):
    """Admin can soft-delete a record (204)."""
    resp = await client.delete(
        "/financial-records/1",
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )
    assert resp.status_code == 204


async def test_soft_deleted_does_not_appear_in_list(
    client: AsyncClient, tokens: dict
):
    """Soft-deleted records are excluded from listing and summary."""
    resp = await client.get(
        "/financial-records/",
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )
    assert resp.status_code == 200
    records = resp.json()
    assert not any(r["id"] == 1 for r in records)

    resp_sum = await client.get(
        "/financial-records/summary",
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )
    summary = resp_sum.json()
    assert summary["total_income"] == "0.00"

async def test_search_by_category(client: AsyncClient, tokens: dict):
    """Search by category keyword returns matching records."""
    await client.post(
        "/financial-records/",
        json={
            "amount": 420.00,
            "type": "expense",
            "category": "Utilities",
            "date": str(date.today()),
            "notes": "Electric bill for March",
        },
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )
    resp = await client.get(
        "/financial-records/?search=Utilities",
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["amount"] == "420.00"


async def test_search_by_notes_case_insensitive(client: AsyncClient, tokens: dict):
    """Search is case-insensitive and matches against notes."""
    resp = await client.get(
        "/financial-records/?search=electric",
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["notes"] == "Electric bill for March"


async def test_search_no_results(client: AsyncClient, tokens: dict):
    """Search returning no matches still gives 200 with empty list."""
    resp = await client.get(
        "/financial-records/?search=pizza",
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 0

async def test_rate_limiting(client: AsyncClient):
    """Exceeding the login rate limit (5/min) triggers a 429 response."""
    data = {"email": "nobody@example.com", "password": "wrong"}
    resp = None
    for _ in range(10):
        resp = await client.post("/login", json=data)
        if resp.status_code == 429:
            break
    assert resp.status_code == 429
    assert "Rate limit exceeded" in resp.text or "Too Many Requests" in resp.text
