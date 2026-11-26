
def register_and_login(client, email, name):
    client.post("/auth/register", json={
        "email": email,
        "name": name,
        "password": "Haslo123!"
    })

    response = client.post(
        "/auth/login",
        data={
            "username": email,
            "password": "Haslo123!"
        }
    )

    assert response.status_code == 200

    return response.json()["access_token"]


def test_tasks_are_scoped_to_current_user(client):
    token_a = register_and_login(
        client,
        "anna@example.com",
        "Anna"
    )

    token_b = register_and_login(
        client,
        "bartek@example.com",
        "Bartek"
    )

    headers_a = {
        "Authorization": f"Bearer {token_a}"
    }

    headers_b = {
        "Authorization": f"Bearer {token_b}"
    }

    response_a = client.post(
        "/tasks",
        json={
            "title": "Zadanie Anny",
            "completed": False,
            "priority": 1
        },
        headers=headers_a
    )

    response_b = client.post(
        "/tasks",
        json={
            "title": "Zadanie Bartka",
            "completed": False,
            "priority": 2
        },
        headers=headers_b
    )

    assert response_a.status_code == 201
    assert response_b.status_code == 201

    tasks_a = client.get("/tasks", headers=headers_a)

    tasks_b = client.get("/tasks", headers=headers_b)

    assert tasks_a.status_code == 200
    assert tasks_b.status_code == 200

    assert len(tasks_a.json()) == 1
    assert tasks_a.json()[0]["title"] == "Zadanie Anny"

    assert len(tasks_b.json()) == 1
    assert tasks_b.json()[0]["title"] == "Zadanie Bartka"



def test_cannot_update_other_users_task(client):
    token_a = register_and_login(
        client,
        "anna2@example.com",
        "Anna"
    )

    token_b = register_and_login(
        client,
        "bartek2@example.com",
        "Bartek"
    )

    headers_a = {
        "Authorization": f"Bearer {token_a}"
    }

    headers_b = {
        "Authorization": f"Bearer {token_b}"
    }

    create_response = client.post(
        "/tasks",
        json={
            "title": "Prywatne zadanie Bartka",
            "completed": False,
            "priority": 2
        },
        headers=headers_b
    )

    task_id = create_response.json()["id"]

    response = client.put(
        f"/tasks/{task_id}",
        json={
            "title": "Zmienione przez Annę",
            "completed": True,
            "priority": 3
        },
        headers=headers_a
    )

    assert create_response.status_code == 201
    assert response.status_code == 403


def test_cannot_delete_other_users_task(client):
    token_a = register_and_login(
        client,
        "anna3@example.com",
        "Anna"
    )

    token_b = register_and_login(
        client,
        "bartek3@example.com",
        "Bartek"
    )

    headers_a = {
        "Authorization": f"Bearer {token_a}"
    }

    headers_b = {
        "Authorization": f"Bearer {token_b}"
    }

    create_response = client.post(
        "/tasks",
        json={
            "title": "Zadanie do ochrony",
            "completed": False,
            "priority": 1
        },
        headers=headers_b
    )

    task_id = create_response.json()["id"]

    response = client.delete(
        f"/tasks/{task_id}",
        headers=headers_a
    )

    assert create_response.status_code == 201
    assert response.status_code == 403

