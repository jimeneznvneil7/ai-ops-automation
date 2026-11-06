
import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    """
    Gumamit ng separate temporary database para
    hindi maapektuhan ang original tickets.db.
    """
    test_db = tmp_path / "test_tickets.db"
    monkeypatch.setattr(main, "DB_PATH", test_db)

    with TestClient(main.app) as test_client:
        yield test_client


# ==========================================
# TEST 1: HEALTH CHECK
# ==========================================

def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "healthy"
    assert data["database"] == "connected"


# ==========================================
# TEST 2: CREATE TICKET
# ==========================================

def test_create_ticket(client):
    response = client.post(
        "/tickets",
        json={
            "title": "VPN connection failure",
            "description": "Cannot connect to company VPN.",
            "requester": "Training User"
        }
    )

    assert response.status_code == 201

    data = response.json()

    assert data["title"] == "VPN connection failure"
    assert data["requester"] == "Training User"
    assert "id" in data


# ==========================================
# TEST 3: GET ALL TICKETS
# ==========================================

def test_get_tickets(client):
    client.post(
        "/tickets",
        json={
            "title": "Computer problem",
            "description": "Computer cannot start.",
            "requester": "Training User"
        }
    )

    response = client.get("/tickets")

    assert response.status_code == 200
    assert len(response.json()) >= 1


# ==========================================
# TEST 4: GET SINGLE TICKET
# ==========================================

def test_get_single_ticket(client):
    create_response = client.post(
        "/tickets",
        json={
            "title": "Internet problem",
            "description": "No internet connection.",
            "requester": "Training User"
        }
    )

    ticket_id = create_response.json()["id"]

    response = client.get(f"/tickets/{ticket_id}")

    assert response.status_code == 200
    assert response.json()["id"] == ticket_id


# ==========================================
# TEST 5: INVALID TICKET ID
# ==========================================

def test_get_missing_ticket(client):
    response = client.get("/tickets/99999")

    assert response.status_code == 404


# ==========================================
# TEST 6: AI SUGGESTION
# ==========================================

def test_ai_suggestion(client):
    create_response = client.post(
        "/tickets",
        json={
            "title": "VPN connection failure",
            "description": "Cannot connect to company VPN.",
            "requester": "Training User"
        }
    )

    ticket_id = create_response.json()["id"]

    response = client.post(
        f"/tickets/{ticket_id}/ai-suggestion"
    )

    assert response.status_code == 200
    assert response.json() is not None


# ==========================================
# TEST 7: MISSING TICKET AI SUGGESTION
# ==========================================

def test_ai_suggestion_missing_ticket(client):
    response = client.post(
        "/tickets/99999/ai-suggestion"
    )

    assert response.status_code == 404


# ==========================================
# TEST 8: TICKET PRIORITY UPDATE
# ==========================================

def test_update_ticket_priority(client):
    create_response = client.post(
        "/tickets",
        json={
            "title": "Computer problem",
            "description": "Computer cannot start.",
            "requester": "Training User"
        }
    )

    ticket_id = create_response.json()["id"]

    response = client.patch(
        f"/tickets/{ticket_id}/priority",
        json={
            "priority": "high"
        }
    )

    assert response.status_code == 200
    assert response.json()["priority"] == "high"


# ==========================================
# TEST 9: REPORT SUMMARY
# ==========================================

def test_report_summary(client):
    client.post(
        "/tickets",
        json={
            "title": "Network problem",
            "description": "Cannot connect to network.",
            "requester": "Training User"
        }
    )

    response = client.get("/reports/summary")

    assert response.status_code == 200

    data = response.json()

    assert "total_tickets" in data
    assert "by_status" in data
    assert "by_priority" in data
    assert "by_category" in data


# ==========================================
# TEST 10: INVALID TICKET UPDATE
# ==========================================

def test_update_missing_ticket(client):
    response = client.patch(
        "/tickets/99999",
        json={
            "status": "closed"
        }
    )

    assert response.status_code == 404
