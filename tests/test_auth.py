
def test_register(client):
    r = client.post("/auth/register", json={
        "email": "a@example.com",
        "name": "Anna",
        "password": "Haslo123!"
    })

    assert r.status_code == 201
    assert "password" not in r.json()
    assert "hashed_password" not in r.json()


def test_short_password_is_422(client):
    r = client.post("/auth/register", json={
        "email": "b@example.com",
        "name": "Bartek",
        "password": "123"
    })

    assert r.status_code == 422


def test_duplicate_email(client):
    data = {
        "email": "duplicate@example.com",
        "name": "Anna",
        "password": "Haslo123!"
    }

    first_response = client.post("/auth/register", json=data)
    second_response = client.post("/auth/register", json=data)

    assert first_response.status_code == 201
    assert second_response.status_code == 409


def test_login_and_me(client):
    client.post("/auth/register", json={
        "email": "login@example.com",
        "name": "Jan",
        "password": "Haslo123!"
    })

    login_response = client.post(
        "/auth/login",
        data={
            "username": "login@example.com",
            "password": "Haslo123!"
        }
    )

    assert login_response.status_code == 200

    token = login_response.json()["access_token"]

    me_response = client.get(
        "/users/me",
        headers={
            "Authorization": f"Bearer {token}"
        }
    )

    assert me_response.status_code == 200
    assert me_response.json()["email"] == "login@example.com"


def test_protected_without_token(client):
    r = client.get("/users/me")

    assert r.status_code == 401
