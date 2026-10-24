from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

import models
from database import get_db
from security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")


def current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    user_id = decode_token(token)
    user = db.get(models.User, user_id) if user_id else None
    if not user:
        raise HTTPException(status_code=401, detail="Please log in again")
    return user