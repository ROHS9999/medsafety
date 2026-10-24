from database import SessionLocal
import models

db = SessionLocal()
for user in db.query(models.User).all():
    print(user.id, user.email, user.hashed_password)
db.close()