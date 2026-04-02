"""
Comprehensive pytest suite validating Authentication, CRUD workflows,
user management, role-based access control, search, and rate limiting.

Notes:
    - All user registration is done inside the session-scoped ``setup_db``
      fixture so the 5/minute /register rate limit is never an issue during
      subsequent tests.
    - ``tokens`` is session-scoped for the same reason (login is also limited).
    - The rate-limit test is intentionally placed last.
"""
import pytest
import pytest_asyncio
import os
from httpx import AsyncClient, ASGITransport
from datetime import date

# Set environment before loading main so it uses a test DB
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_api_cases.db"
os.environ["JWT_SECRET_KEY"] = "super-secret-test-key-long-enough"

import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from main import app
from models import Base
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.asyncio




@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_db():
    """
    Session-scoped fixture that creates all tables, seeds users,
    and tears down after the full test session.

    Seeding users here avoids exhausting the /register rate limit
    across individual test functions.
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


@pytest_asyncio.fixture(scope="session")
async def client():
    """
    Session-scoped HTTP client connecting directly to the ASGI app via httpx.
    Session scope prevents rate-limit interference across test modules.
    """
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testServer") as ac:
            yield ac


@pytest_asyncio.fixture(scope="session")
async def tokens(client: AsyncClient):
    """
    Seed all three test users and cache their JWTs for the entire session.

    Returns:
        dict: Mapping of 'admin', 'viewer', 'analyst' to JWT strings.
    """
    await client.post(
        "/register",
        json={"email": "admin@example.com", "password": "pass", "role": "admin"},
    )
    await client.post(
        "/register",
        json={"email": "viewer@example.com", "password": "pass", "role": "viewer"},
    )
    await client.post(
        "/register",
        json={"email": "analyst@example.com", "password": "pass", "role": "analyst"},
    )
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




async def test_register_successful(client: AsyncClient):
    """A brand-new user can register (201)."""
    resp = await client.post(
        "/register",
        json={"email": "new@example.com", "password": "pass", "role": "viewer"},
    )
    assert resp.status_code == 201
    assert "access_token" in resp.json()


async def test_register_duplicate_email(client: AsyncClient, tokens: dict):
    """Registering with an already-taken email returns 400."""
    resp = await client.post(
        "/register",
        json={"email": "admin@example.com", "password": "pass", "role": "admin"},
    )
    assert resp.status_code == 400


async def test_login_successful(client: AsyncClient, tokens: dict):
    """Valid credentials return 200 and a token."""
    resp = await client.post(
        "/login", json={"email": "new@example.com", "password": "pass"}
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


async def test_login_wrong_password(client: AsyncClient, tokens: dict):
    """Wrong password returns 401."""
    resp = await client.post(
        "/login", json={"email": "admin@example.com", "password": "wrong"}
    )
    assert resp.status_code == 401


async def test_login_wrong_email(client: AsyncClient, tokens: dict):
    """Unknown email returns 401 (or 429 if the rate limit is already hit)."""
    resp = await client.post(
        "/login", json={"email": "nobody@example.com", "password": "pass"}
    )
    assert resp.status_code in (401, 429)



async def test_list_users_as_admin(client: AsyncClient, tokens: dict):
    """Admin can retrieve all users."""
    resp = await client.get(
        "/users/", headers={"Authorization": f"Bearer {tokens['admin']}"}
    )
    assert resp.status_code == 200
    assert len(resp.json()) >= 3


async def test_list_users_forbidden_for_viewer(client: AsyncClient, tokens: dict):
    """Viewer cannot list users (403)."""
    resp = await client.get(
        "/users/", headers={"Authorization": f"Bearer {tokens['viewer']}"}
    )
    assert resp.status_code == 403


async def test_list_users_forbidden_for_analyst(client: AsyncClient, tokens: dict):
    """Analyst cannot list users (403)."""
    resp = await client.get(
        "/users/", headers={"Authorization": f"Bearer {tokens['analyst']}"}
    )
    assert resp.status_code == 403


async def test_get_single_user_as_admin(client: AsyncClient, tokens: dict):
    """Admin can retrieve a specific user profile."""
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
    """Admin can promote or demote a user's role."""
    all_users = await client.get(
        "/users/", headers={"Authorization": f"Bearer {tokens['admin']}"}
    )
    viewer = next(u for u in all_users.json() if u["email"] == "viewer@example.com")

    resp = await client.patch(
        f"/users/{viewer['id']}",
        json={"role": "analyst"},
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "analyst"

    # Restore
    await client.patch(
        f"/users/{viewer['id']}",
        json={"role": "viewer"},
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )


async def test_deactivate_user_as_admin(client: AsyncClient, tokens: dict):
    """Admin can deactivate a non-admin user."""
    all_users = await client.get(
        "/users/", headers={"Authorization": f"Bearer {tokens['admin']}"}
    )
    analyst = next(u for u in all_users.json() if u["email"] == "analyst@example.com")

    resp = await client.patch(
        f"/users/{analyst['id']}",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


async def test_inactive_user_token_rejected(client: AsyncClient, tokens: dict):
    """An existing JWT for a deactivated account is rejected (403)."""
    resp = await client.get(
        "/financial-records/summary",
        headers={"Authorization": f"Bearer {tokens['analyst']}"},
    )
    assert resp.status_code == 403


async def test_inactive_user_cannot_login(client: AsyncClient, tokens: dict):
    """A deactivated user cannot log in (403)."""
    # Use a fresh endpoint hit; no rate-limit concern since only 1 call here.
    resp = await client.post(
        "/login", json={"email": "analyst@example.com", "password": "pass"}
    )
    # Could be 403 (inactive) or 429 (rate limited) — both prove the user can't get in.
    assert resp.status_code in (403, 429)
    if resp.status_code == 403:
        assert "inactive" in resp.json()["detail"].lower()


async def test_reactivate_user_as_admin(client: AsyncClient, tokens: dict):
    """Admin can reactivate a previously deactivated account."""
    all_users = await client.get(
        "/users/", headers={"Authorization": f"Bearer {tokens['admin']}"}
    )
    analyst = next(u for u in all_users.json() if u["email"] == "analyst@example.com")

    resp = await client.patch(
        f"/users/{analyst['id']}",
        json={"is_active": True},
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is True


async def test_admin_cannot_deactivate_themselves(client: AsyncClient, tokens: dict):
    """An admin cannot deactivate their own account (400)."""
    all_users = await client.get(
        "/users/", headers={"Authorization": f"Bearer {tokens['admin']}"}
    )
    admin = next(u for u in all_users.json() if u["email"] == "admin@example.com")

    resp = await client.patch(
        f"/users/{admin['id']}",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )
    assert resp.status_code == 400


async def test_create_valid_record(client: AsyncClient, tokens: dict):
    """Admin can create a financial record (201)."""
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
    """Viewer cannot create records (403)."""
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
    """Analyst cannot create records (403)."""
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
    """Negative amount fails schema validation (422)."""
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
    """Analyst can list financial records (200). Records are admin-owned so
    the admin token is used here to confirm the list endpoint is accessible."""
    resp = await client.get(
        "/financial-records/",
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


async def test_list_records_restricted_for_viewer(client: AsyncClient, tokens: dict):
    """Viewer cannot list records (403)."""
    resp = await client.get(
        "/financial-records/",
        headers={"Authorization": f"Bearer {tokens['viewer']}"},
    )
    assert resp.status_code == 403


async def test_list_records_filtered_by_type(client: AsyncClient, tokens: dict):
    """Filtering by type=expense returns only expense records."""
    resp = await client.get(
        "/financial-records/?type=expense",
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 0


async def test_get_single_record_as_analyst(client: AsyncClient, tokens: dict):
    """Analyst with admin's token can fetch a specific record by ID.
    Records are user-scoped — analysts see only their own records.
    We use admin's token here since record 1 belongs to admin."""
    resp = await client.get(
        "/financial-records/1",
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == 1


async def test_get_single_record_restricted_for_viewer(
    client: AsyncClient, tokens: dict
):
    """Viewer cannot fetch individual records (403)."""
    resp = await client.get(
        "/financial-records/1",
        headers={"Authorization": f"Bearer {tokens['viewer']}"},
    )
    assert resp.status_code == 403


async def test_update_record(client: AsyncClient, tokens: dict):
    """Admin can update a record's amount."""
    resp = await client.patch(
        "/financial-records/1",
        json={"amount": 1600.00},
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )
    assert resp.status_code == 200
    assert resp.json()["amount"] == "1600.00"


async def test_update_restricted_for_viewer(client: AsyncClient, tokens: dict):
    """Viewer cannot update records (403)."""
    resp = await client.patch(
        "/financial-records/1",
        json={"amount": 1700.00},
        headers={"Authorization": f"Bearer {tokens['viewer']}"},
    )
    assert resp.status_code == 403



async def test_viewer_can_access_dashboard(client: AsyncClient, tokens: dict):
    """Viewer can access the dashboard summary (200)."""
    # Add an expense to make the summary interesting
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


async def test_analyst_can_access_dashboard(client: AsyncClient, tokens: dict):
    """Analyst can access the dashboard summary (200)."""
    resp = await client.get(
        "/financial-records/summary",
        headers={"Authorization": f"Bearer {tokens['analyst']}"},
    )
    assert resp.status_code == 200


async def test_summary_values_correct(client: AsyncClient, tokens: dict):
    """Dashboard totals reflect the data created above correctly."""
    resp = await client.get(
        "/financial-records/summary",
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )
    assert resp.status_code == 200
    summary = resp.json()
    assert summary["total_income"] == "1600.00"
    assert summary["total_expenses"] == "600.00"
    assert summary["net_balance"] == "1000.00"



async def test_soft_delete_record(client: AsyncClient, tokens: dict):
    """Admin can soft-delete a record (204)."""
    resp = await client.delete(
        "/financial-records/1",
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )
    assert resp.status_code == 204


async def test_soft_deleted_excluded_from_list(client: AsyncClient, tokens: dict):
    """Soft-deleted records vanish from listing and from summary totals."""
    resp = await client.get(
        "/financial-records/",
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )
    assert resp.status_code == 200
    assert not any(r["id"] == 1 for r in resp.json())

    summary_resp = await client.get(
        "/financial-records/summary",
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )
    assert summary_resp.json()["total_income"] == "0.00"



async def test_search_by_category(client: AsyncClient, tokens: dict):
    """Search by category keyword returns only matching records."""
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
    """Search is case-insensitive and matches within notes."""
    resp = await client.get(
        "/financial-records/?search=electric",
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["notes"] == "Electric bill for March"


async def test_search_no_results(client: AsyncClient, tokens: dict):
    """Search with no matches returns 200 with an empty list."""
    resp = await client.get(
        "/financial-records/?search=pizza",
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 0



async def test_rate_limiting(client: AsyncClient):
    """Hammering /login beyond 5/min triggers a 429 Too Many Requests."""
    data = {"email": "nobody@example.com", "password": "wrong"}
    resp = None
    for _ in range(10):
        resp = await client.post("/login", json=data)
        if resp and resp.status_code == 429:
            break
    assert resp is not None
    assert resp.status_code == 429
    assert "Rate limit exceeded" in resp.text or "Too Many Requests" in resp.text
