"""Auth helpers — auth disabled, returns default dev user for all requests."""


def get_current_user() -> dict:
    return {"sub": "dev-user", "email": "dev@northwindlogistics.com"}


def get_current_user_id() -> str:
    return "dev-user"
