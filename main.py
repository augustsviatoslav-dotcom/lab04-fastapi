import logging
import os
import time
import redis

from fastapi import Request, Depends, FastAPI, HTTPException, Query, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models import Task, User
from schemas import (
    TaskCreate,
    TaskRead,
    TaskUpdate,
    UserCreate,
    UserRegister,
    UserRead,
    Token
)
from auth import (
    hash_password,
    create_access_token,
    verify_password,
    get_current_user
)


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

logger = logging.getLogger("api")


app = FastAPI(title="Lab 02 - Database API", version="2.0")


redis_client = redis.Redis.from_url(
    os.getenv("REDIS_URL", "redis://redis:6379/0"),
    decode_responses=True,
)


@app.middleware("http")
async def request_logger(request: Request, call_next):
    start = time.perf_counter()

    response = await call_next(request)

    ms = (time.perf_counter() - start) * 1000

    logger.info(
        "%s %s -> %s %.1fms",
        request.method,
        request.url.path,
        response.status_code,
        ms,
    )

    return response


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stats/requests")
def get_request_count():
    count = redis_client.incr("api:requests")

    if count == 1:
        redis_client.expire("api:requests", 60)

    return {
        "requests": count,
        "ttl_seconds": 60
    }


@app.post(
    "/users",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED
)
def create_user(
    user_data: UserCreate,
    db: Session = Depends(get_db)
):
    user = User(**user_data.model_dump())

    db.add(user)

    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already exists"
        )

    return user


@app.get(
    "/users",
    response_model=list[UserRead],
    status_code=status.HTTP_200_OK
)
def get_users(db: Session = Depends(get_db)):
    query = select(User).order_by(User.id)
    users = db.scalars(query).all()

    return users

@app.get("/users/me", response_model=UserRead)
def read_me(
    current_user: User = Depends(get_current_user)
):
    return current_user

@app.get(
    "/users/{user_id}",
    response_model=UserRead,
    status_code=status.HTTP_200_OK
)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return user


def require_task_owner(task: Task, current_user: User) -> None:
    if task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not allowed to access this task"
        )

@app.post(
    "/tasks",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED
)
def create_task(
    task_data: TaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    task_data_dict = task_data.model_dump()
    task_data_dict["user_id"] = current_user.id

    task = Task(**task_data_dict)

    db.add(task)
    db.commit()
    db.refresh(task)

    return task



@app.get(
    "/tasks",
    response_model=list[TaskRead],
    status_code=status.HTTP_200_OK
)
def get_tasks(
    completed: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = select(Task).where(Task.user_id == current_user.id)

    if completed is not None:
        query = query.where(Task.completed == completed)

    offset = (page - 1) * page_size
    query = query.order_by(Task.id).offset(offset).limit(page_size)

    tasks = db.scalars(query).all()

    return tasks


@app.get(
    "/tasks/{task_id}",
    response_model=TaskRead,
    status_code=status.HTTP_200_OK
)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    task = db.get(Task, task_id)

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )

    require_task_owner(task, current_user)

    return task




@app.put(
    "/tasks/{task_id}",
    response_model=TaskRead,
    status_code=status.HTTP_200_OK
)
def update_task(
    task_id: int,
    task_data: TaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    task = db.get(Task, task_id)

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )

    require_task_owner(task, current_user)

    update_data = task_data.model_dump(exclude_unset=True)

    # Nie pozwalamy zmieniać właściciela zadania
    update_data.pop("user_id", None)

    for field, value in update_data.items():
        setattr(task, field, value)

    db.commit()
    db.refresh(task)

    return task



@app.delete(
    "/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    task = db.get(Task, task_id)

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )

    require_task_owner(task, current_user)

    db.delete(task)
    db.commit()



@app.get(
    "/users/{user_id}/tasks",
    response_model=list[TaskRead],
    status_code=status.HTTP_200_OK
)
def get_user_tasks(
    user_id: int,
    db: Session = Depends(get_db)
):
    user = db.get(User, user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    query = select(Task).where(Task.user_id == user_id)
    tasks = db.scalars(query).all()

    return tasks


@app.post(
    "/auth/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED
)
def register_user(
    data: UserRegister,
    db: Session = Depends(get_db)
):
    existing_user = db.scalar(
        select(User).where(User.email == data.email)
    )

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered"
        )

    new_user = User(
        name=data.name,
        email=data.email,
        hashed_password=hash_password(data.password)
    )

    db.add(new_user)

    try:
        db.commit()
        db.refresh(new_user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered"
        )

    return new_user


@app.post("/auth/login", response_model=Token)
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = db.scalar(
        select(User).where(User.email == form.username)
    )

    if not user or not user.hashed_password or not verify_password(
        form.password, user.hashed_password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"}
        )

    return {
        "access_token": create_access_token(user.email),
        "token_type": "bearer"
    }






# TODO 1: POST /users
# TODO 2: GET /users
# TODO 3: GET /users/{user_id}
# TODO 4: POST /tasks
# TODO 5: GET /tasks z filtrami i paginacja
# TODO 6: GET /tasks/{task_id}
# TODO 7: PUT /tasks/{task_id}
# TODO 8: DELETE /tasks/{task_id}
# TODO 9: GET /users/{user_id}/tasks