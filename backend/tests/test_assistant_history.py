from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.db.session import get_db
from app.main import app
from app.models import User, UserRole
from app.models.assistant import AssistantMessage


def test_history_is_private_to_its_administrator(db):
    first = User(
        email="first@example.test", full_name="Primeiro", password_hash="test", role=UserRole.admin
    )
    second = User(
        email="second@example.test", full_name="Segundo", password_hash="test", role=UserRole.admin
    )
    operator = User(
        email="operator@example.test",
        full_name="Operador",
        password_hash="test",
        role=UserRole.operator,
    )
    db.add_all([first, second, operator])
    db.commit()
    current = [first]
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: current[0]
    try:
        with TestClient(app) as client:
            created = client.post("/api/v1/assistant/conversations")
            assert created.status_code == 201
            assert created.json()["created_at"].endswith("Z")
            conversation_id = created.json()["id"]
            db.add(AssistantMessage(conversation_id=conversation_id, role="user", content="teste"))
            db.commit()
            assert (
                client.get(f"/api/v1/assistant/conversations/{conversation_id}").json()["messages"][
                    0
                ]["content"]
                == "teste"
            )
            current[0] = second
            assert client.get("/api/v1/assistant/conversations").json() == []
            assert (
                client.get(f"/api/v1/assistant/conversations/{conversation_id}").status_code == 404
            )
            assert (
                client.delete(f"/api/v1/assistant/conversations/{conversation_id}").status_code
                == 404
            )
            current[0] = operator
            assert client.get("/api/v1/assistant/conversations").status_code == 403
            assert client.post("/api/v1/assistant/conversations").status_code == 403
            assert (
                client.get(f"/api/v1/assistant/conversations/{conversation_id}").status_code == 403
            )
            assert (
                client.delete(f"/api/v1/assistant/conversations/{conversation_id}").status_code
                == 403
            )
            current[0] = first
            assert (
                client.delete(f"/api/v1/assistant/conversations/{conversation_id}").status_code
                == 204
            )
            assert (
                client.get(f"/api/v1/assistant/conversations/{conversation_id}").status_code == 404
            )
            assert db.query(AssistantMessage).count() == 0
    finally:
        app.dependency_overrides.clear()
