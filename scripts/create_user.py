"""CLI script to create a user account."""

import argparse
import sys

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import User
from app.services.auth_service import hash_password


MIN_PASSWORD_LENGTH = 12


def create_user(username: str, password: str, display_name: str | None = None) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"Error: Password must be at least {MIN_PASSWORD_LENGTH} characters.")
        sys.exit(1)

    db: Session = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            print(f"Error: User '{username}' already exists.")
            sys.exit(1)

        user = User(
            username=username,
            hashed_password=hash_password(password),
            display_name=display_name,
        )
        db.add(user)
        db.commit()
        print(f"User '{username}' created successfully (id={user.id}).")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create a user account")
    parser.add_argument("--username", required=True, help="Username")
    parser.add_argument("--password", required=True, help="Password")
    parser.add_argument("--display-name", help="Display name (optional)")
    args = parser.parse_args()

    create_user(args.username, args.password, args.display_name)
