from sqlalchemy import Boolean, Column, Date, Float, ForeignKey, Integer, String
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)


class Profile(Base):
    __tablename__ = "profiles"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    full_name = Column(String, nullable=False)
    age = Column(Integer, nullable=True)
    sex = Column(String, nullable=True)
    blood_group = Column(String, nullable=True)
    is_pregnant = Column(Boolean, nullable=True)
    kidney_egfr = Column(Float, nullable=True)
    liver_note = Column(String, nullable=True)


class Condition(Base):
    __tablename__ = "conditions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    name = Column(String, nullable=False)
    severity = Column(String, nullable=True)
    acuity_type = Column(String, nullable=False)
    status = Column(String, nullable=False, default="ongoing")
    diagnosed_date = Column(Date, nullable=True)
    resolved_date = Column(Date, nullable=True)

    

class Allergy(Base):
    __tablename__ = "allergies"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    substance = Column(String, nullable=False)
    reaction = Column(String, nullable=True)
    severity = Column(String, nullable=True)



class LabResult(Base):
    __tablename__ = "lab_results"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    test_name = Column(String, nullable=False)
    value = Column(Float, nullable=False)
    unit = Column(String, nullable=True)
    taken_on = Column(Date, nullable=False)
    reference_low = Column(Float, nullable=True)
    reference_high = Column(Float, nullable=True)   

    

class Doctor(Base):
    __tablename__ = "doctors"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    name = Column(String, nullable=False)
    speciality = Column(String, nullable=True)
    clinic = Column(String, nullable=True)
    phone = Column(String, nullable=True)



class Prescription(Base):
    __tablename__ = "prescriptions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=True)
    prescription_date = Column(Date, nullable=False)
    file_path = Column(String, nullable=True)
    notes = Column(String, nullable=True)

    

class Medicine(Base):
    __tablename__ = "medicines"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    prescription_id = Column(Integer, ForeignKey("prescriptions.id"), index=True, nullable=False)
    name = Column(String, nullable=False)
    salt_name = Column(String, nullable=True)
    strength = Column(String, nullable=True)
    dose = Column(String, nullable=True)
    frequency = Column(String, nullable=True)
    duration_days = Column(Integer, nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    half_life_hours = Column(Float, nullable=True)
    confirmed = Column(Boolean, nullable=False, default=True)