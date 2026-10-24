from database import SessionLocal, Base, engine
import models

Base.metadata.create_all(bind=engine)

db = SessionLocal()

user = models.User(email="test@example.com", hashed_password="placeholder")
db.add(user)
db.commit()
db.refresh(user)
print("Saved a user with id:", user.id)

found = db.query(models.User).filter(models.User.email == "test@example.com").first()
print("Read it back:", found.email)

db.delete(found)
db.commit()
print("Deleted the test user. The database works.")

db.close()