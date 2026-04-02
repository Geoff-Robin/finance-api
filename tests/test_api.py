"""
Comprehensive pytest suite validating Authentication, CRUD workflows, filtering, summary generation, and rate limits.
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
    Module-scoped HTTP client fixture connecting directly to the ASGI app via `httpx`.
    Ensures standard FastAPI lifespan context initialization occurs.
    """
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testServer") as ac:
            yield ac


async def test_register_successful(client: AsyncClient):
    resp = await client.post("/register", json={"email": "admin@example.com", "password": "pass", "role": "admin"})
    assert resp.status_code == 201
    assert "access_token" in resp.json()

async def test_register_duplicate_email(client: AsyncClient):
    resp = await client.post("/register", json={"email": "admin@example.com", "password": "pass", "role": "admin"})
    assert resp.status_code == 400

async def test_login_successful(client: AsyncClient):
    resp = await client.post("/login", json={"email": "admin@example.com", "password": "pass"})
    assert resp.status_code == 200
    assert "access_token" in resp.json()

async def test_login_wrong_password(client: AsyncClient):
    resp = await client.post("/login", json={"email": "admin@example.com", "password": "wrong"})
    assert resp.status_code == 401

async def test_login_wrong_email(client: AsyncClient):
    resp = await client.post("/login", json={"email": "nobody@example.com", "password": "pass"})
    assert resp.status_code == 401


@pytest_asyncio.fixture(scope="module")
async def tokens(client: AsyncClient):
    """
    Sets up mocked users, signs them in, and caches JWTs to reduce duplicate endpoint hits.

    Args:
        client (AsyncClient): Client abstraction linking to the backend.

    Returns:
        dict: A mapping of active 'admin' and 'viewer' JWT strings.
    """
    await client.post("/register", json={"email": "viewer@example.com", "password": "pass", "role": "viewer"})
    viewer_resp = await client.post("/login", json={"email": "viewer@example.com", "password": "pass"})
    
    admin_resp = await client.post("/login", json={"email": "admin@example.com", "password": "pass"})
    
    return {
        "admin": admin_resp.json()["access_token"],
        "viewer": viewer_resp.json()["access_token"]
    }


async def test_create_valid_record(client: AsyncClient, tokens: dict):
    data = {
        "amount": 1500.00,
        "type": "income",
        "category": "Salary",
        "date": str(date.today()),
        "notes": "Test salary"
    }
    resp = await client.post("/financial-records/", json=data, headers={"Authorization": f"Bearer {tokens['admin']}"})
    assert resp.status_code == 201
    assert resp.json()["amount"] == "1500.00"

async def test_create_restricted_by_role(client: AsyncClient, tokens: dict):
    data = {"amount": 50.00, "type": "expense", "category": "Food", "date": str(date.today())}
    resp = await client.post("/financial-records/", json=data, headers={"Authorization": f"Bearer {tokens['viewer']}"})
    assert resp.status_code == 403

async def test_create_invalid_data(client: AsyncClient, tokens: dict):
    data = {"amount": -100.00, "type": "expense", "category": "Food", "date": str(date.today())}
    resp = await client.post("/financial-records/", json=data, headers={"Authorization": f"Bearer {tokens['admin']}"})
    assert resp.status_code == 422

async def test_list_records(client: AsyncClient, tokens: dict):
    resp = await client.get("/financial-records/", headers={"Authorization": f"Bearer {tokens['admin']}"})
    assert resp.status_code == 200
    assert len(resp.json()) >= 1

async def test_list_records_filtered(client: AsyncClient, tokens: dict):
    resp = await client.get("/financial-records/?type=expense", headers={"Authorization": f"Bearer {tokens['admin']}"})
    assert resp.status_code == 200
    assert len(resp.json()) == 0 

async def test_get_single_record(client: AsyncClient, tokens: dict):
    resp = await client.get("/financial-records/1", headers={"Authorization": f"Bearer {tokens['admin']}"})
    assert resp.status_code == 200
    assert resp.json()["id"] == 1

async def test_prevent_retrieving_another_user_record(client: AsyncClient, tokens: dict):
    resp = await client.get("/financial-records/1", headers={"Authorization": f"Bearer {tokens['viewer']}"})
    assert resp.status_code == 404

async def test_update_record(client: AsyncClient, tokens: dict):
    resp = await client.patch("/financial-records/1", json={"amount": 1600.00}, headers={"Authorization": f"Bearer {tokens['admin']}"})
    assert resp.status_code == 200
    assert resp.json()["amount"] == "1600.00"

async def test_update_restricted_by_role(client: AsyncClient, tokens: dict):
    resp = await client.patch("/financial-records/1", json={"amount": 1700.00}, headers={"Authorization": f"Bearer {tokens['viewer']}"})
    assert resp.status_code == 403

async def test_get_dashboard_summary(client: AsyncClient, tokens: dict):
    await client.post("/financial-records/", 
                      json={"amount": 600.00, "type": "expense", "category": "Rent", "date": str(date.today())}, 
                      headers={"Authorization": f"Bearer {tokens['admin']}"})
    
    resp = await client.get("/financial-records/summary", headers={"Authorization": f"Bearer {tokens['admin']}"})
    assert resp.status_code == 200
    summary = resp.json()
    assert summary["total_income"] == "1600.00"
    assert summary["total_expenses"] == "600.00"
    assert summary["net_balance"] == "1000.00"

async def test_summary_restricted_by_role(client: AsyncClient, tokens: dict):
    resp = await client.get("/financial-records/summary", headers={"Authorization": f"Bearer {tokens['viewer']}"})
    assert resp.status_code == 403

async def test_soft_delete_record(client: AsyncClient, tokens: dict):
    resp = await client.delete("/financial-records/1", headers={"Authorization": f"Bearer {tokens['admin']}"})
    assert resp.status_code == 204

async def test_soft_deleted_does_not_appear(client: AsyncClient, tokens: dict):
    resp = await client.get("/financial-records/", headers={"Authorization": f"Bearer {tokens['admin']}"})
    assert resp.status_code == 200
    records = resp.json()
    assert not any(r["id"] == 1 for r in records)
    resp_sum = await client.get("/financial-records/summary", headers={"Authorization": f"Bearer {tokens['admin']}"})
    summary = resp_sum.json()
    assert summary["total_income"] == "0.00"

async def test_search_support(client: AsyncClient, tokens: dict):
    await client.post("/financial-records/", 
                      json={"amount": 420.00, "type": "expense", "category": "Utilities", "date": str(date.today()), "notes": "Electric bill for March"}, 
                      headers={"Authorization": f"Bearer {tokens['admin']}"})
    
    resp = await client.get("/financial-records/?search=Utilities", headers={"Authorization": f"Bearer {tokens['admin']}"})
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["amount"] == "420.00"

    resp2 = await client.get("/financial-records/?search=electric", headers={"Authorization": f"Bearer {tokens['admin']}"})
    assert resp2.status_code == 200
    assert len(resp2.json()) == 1
    assert resp2.json()[0]["notes"] == "Electric bill for March"

    resp3 = await client.get("/financial-records/?search=pizza", headers={"Authorization": f"Bearer {tokens['admin']}"})
    assert resp3.status_code == 200
    assert len(resp3.json()) == 0

async def test_rate_limiting(client: AsyncClient):
    data = {"email": "nobody@example.com", "password": "wrong"}
    for _ in range(6):
        resp = await client.post("/login", json=data)
        if resp.status_code == 429:
            break
            
    assert resp.status_code == 429
    assert "Rate limit exceeded" in resp.text or "Too Many Requests" in resp.text

