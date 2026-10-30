import os
import uuid
from datetime import date, timedelta
from typing import Literal, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordRequestForm


from sqlalchemy import func, or_
from sqlalchemy.orm import Session

import models
from database import Base, engine, get_db
from deps import current_user

from schemas import (
    AllergyIn,
    AllergyOut,
    ConditionIn,
    ConditionOut,
    DoctorIn,
    DoctorOut,
    LabIn,
    LabOut,
    MedicineIn,
    MedicineOut,
    PrescriptionOut,
    ProfileIn,
    ProfileOut,
    SignupIn,
    TokenOut,
    UserOut,
)

from security import create_token, hash_password, verify_password

Base.metadata.create_all(bind=engine)

app = FastAPI()


@app.get("/health")
def health():
    return {"status": "running"}


@app.post("/signup", response_model=UserOut, status_code=201)
def signup(body: SignupIn, db: Session = Depends(get_db)):
    email = body.email.lower()

    if len(body.password.encode()) > 72:
        raise HTTPException(status_code=400, detail="Password is too long")

    if db.query(models.User).filter(models.User.email == email).first():
        raise HTTPException(status_code=409, detail="This email is already registered")

    user = models.User(email=email, hashed_password=hash_password(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.post("/login", response_model=TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    email = form.username.lower()
    user = db.query(models.User).filter(models.User.email == email).first()

    if (
        not user
        or len(form.password.encode()) > 72
        or not verify_password(form.password, user.hashed_password)
    ):
        raise HTTPException(status_code=401, detail="Wrong email or password")

    return TokenOut(access_token=create_token(user.id))


@app.get("/me", response_model=UserOut)
def me(user: models.User = Depends(current_user)):
    return user


@app.put("/profile", response_model=ProfileOut)
def save_profile(
    body: ProfileIn,
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    profile = db.query(models.Profile).filter(models.Profile.user_id == user.id).first()

    if profile is None:
        profile = models.Profile(user_id=user.id, **body.model_dump())
        db.add(profile)
    else:
        for key, value in body.model_dump().items():
            setattr(profile, key, value)

    db.commit()
    db.refresh(profile)
    return profile


@app.get("/profile", response_model=ProfileOut)
def get_profile(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    profile = db.query(models.Profile).filter(models.Profile.user_id == user.id).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not created yet")
    return profile


@app.post("/conditions", response_model=ConditionOut, status_code=201)
def add_condition(
    body: ConditionIn,
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    condition = models.Condition(user_id=user.id, **body.model_dump())
    db.add(condition)
    db.commit()
    db.refresh(condition)
    return condition


@app.get("/conditions", response_model=list[ConditionOut])
def list_conditions(
    status: Optional[Literal["ongoing", "resolved"]] = None,
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    query = db.query(models.Condition).filter(models.Condition.user_id == user.id)
    if status:
        query = query.filter(models.Condition.status == status)
    return query.order_by(models.Condition.id).all()

def find_condition(db: Session, user: models.User, condition_id: int):
    condition = (
        db.query(models.Condition)
        .filter(models.Condition.id == condition_id, models.Condition.user_id == user.id)
        .first()
    )
    if condition is None:
        raise HTTPException(status_code=404, detail="Illness not found")
    return condition


@app.put("/conditions/{condition_id}", response_model=ConditionOut)
def update_condition(
    condition_id: int,
    body: ConditionIn,
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    condition = find_condition(db, user, condition_id)
    for key, value in body.model_dump().items():
        setattr(condition, key, value)
    db.commit()
    db.refresh(condition)
    return condition


@app.delete("/conditions/{condition_id}", status_code=204)
def delete_condition(
    condition_id: int,
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    condition = find_condition(db, user, condition_id)
    db.delete(condition)
    db.commit()



def allergy_exists(db: Session, user: models.User, substance: str, ignore_id: Optional[int] = None):
    query = db.query(models.Allergy).filter(
        models.Allergy.user_id == user.id,
        func.lower(models.Allergy.substance) == substance.lower(),
    )
    if ignore_id is not None:
        query = query.filter(models.Allergy.id != ignore_id)
    return query.first() is not None


def find_allergy(db: Session, user: models.User, allergy_id: int):
    allergy = (
        db.query(models.Allergy)
        .filter(models.Allergy.id == allergy_id, models.Allergy.user_id == user.id)
        # .filter(models.Allergy.id x== allergy_id)
        .first()
    )
    if allergy is None:
        raise HTTPException(status_code=404, detail="Allergy not found")
    return allergy


@app.post("/allergies", response_model=AllergyOut, status_code=201)
def add_allergy(
    body: AllergyIn,
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if allergy_exists(db, user, body.substance):
        raise HTTPException(status_code=409, detail="You already added this allergy")

    allergy = models.Allergy(user_id=user.id, **body.model_dump())
    db.add(allergy)
    db.commit()
    db.refresh(allergy)
    return allergy


@app.get("/allergies", response_model=list[AllergyOut])
def list_allergies(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    return (
        db.query(models.Allergy)
        .filter(models.Allergy.user_id == user.id)
        .order_by(models.Allergy.id)
        .all()
    )


@app.put("/allergies/{allergy_id}", response_model=AllergyOut)
def update_allergy(
    allergy_id: int,
    body: AllergyIn,
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    allergy = find_allergy(db, user, allergy_id)

    if allergy_exists(db, user, body.substance, ignore_id=allergy.id):
        raise HTTPException(status_code=409, detail="You already added this allergy")

    for key, value in body.model_dump().items():
        setattr(allergy, key, value)
    db.commit()
    db.refresh(allergy)
    return allergy


@app.delete("/allergies/{allergy_id}", status_code=204)
def delete_allergy(
    allergy_id: int,
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    allergy = find_allergy(db, user, allergy_id)
    db.delete(allergy)
    db.commit()



def find_lab(db: Session, user: models.User, lab_id: int):
    lab = (
        db.query(models.LabResult)
        .filter(models.LabResult.id == lab_id, models.LabResult.user_id == user.id)
        .first()
    )
    if lab is None:
        raise HTTPException(status_code=404, detail="Test result not found")
    return lab


@app.post("/labs", response_model=LabOut, status_code=201)
def add_lab(
    body: LabIn,
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    lab = models.LabResult(user_id=user.id, **body.model_dump())
    db.add(lab)
    db.commit()
    db.refresh(lab)
    return lab


@app.get("/labs", response_model=list[LabOut])
def list_labs(
    test_name: Optional[str] = None,
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    query = db.query(models.LabResult).filter(models.LabResult.user_id == user.id)
    if test_name:
        query = query.filter(func.lower(models.LabResult.test_name) == test_name.strip().lower())
    return query.order_by(models.LabResult.taken_on.desc(), models.LabResult.id.desc()).all()


@app.get("/labs/latest", response_model=list[LabOut])
def latest_labs(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    """The newest result for each different test."""
    rows = (
        db.query(models.LabResult)
        .filter(models.LabResult.user_id == user.id)
        .order_by(models.LabResult.taken_on.desc(), models.LabResult.id.desc())
        .all()
    )
    newest = {}
    for row in rows:
        newest.setdefault(row.test_name.lower(), row)
    return list(newest.values())


@app.put("/labs/{lab_id}", response_model=LabOut)
def update_lab(
    lab_id: int,
    body: LabIn,
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    lab = find_lab(db, user, lab_id)
    for key, value in body.model_dump().items():
        setattr(lab, key, value)
    db.commit()
    db.refresh(lab)
    return lab


@app.delete("/labs/{lab_id}", status_code=204)
def delete_lab(
    lab_id: int,
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    lab = find_lab(db, user, lab_id)
    db.delete(lab)
    db.commit()



def find_doctor(db: Session, user: models.User, doctor_id: int):
    doctor = (
        db.query(models.Doctor)
        .filter(models.Doctor.id == doctor_id, models.Doctor.user_id == user.id)
        .first()
    )
    if doctor is None:
        raise HTTPException(status_code=404, detail="Doctor not found")
    return doctor


@app.post("/doctors", response_model=DoctorOut, status_code=201)
def add_doctor(
    body: DoctorIn,
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    doctor = models.Doctor(user_id=user.id, **body.model_dump())
    db.add(doctor)
    db.commit()
    db.refresh(doctor)
    return doctor


@app.get("/doctors", response_model=list[DoctorOut])
def list_doctors(
    q: Optional[str] = None,
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    query = db.query(models.Doctor).filter(models.Doctor.user_id == user.id)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(
                models.Doctor.name.ilike(like),
                models.Doctor.speciality.ilike(like),
                models.Doctor.clinic.ilike(like),
            )
        )
    return query.order_by(func.lower(models.Doctor.name)).all()


@app.put("/doctors/{doctor_id}", response_model=DoctorOut)
def update_doctor(
    doctor_id: int,
    body: DoctorIn,
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    doctor = find_doctor(db, user, doctor_id)
    for key, value in body.model_dump().items():
        setattr(doctor, key, value)
    db.commit()
    db.refresh(doctor)
    return doctor


@app.delete("/doctors/{doctor_id}", status_code=204)
def delete_doctor(
    doctor_id: int,
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    doctor = find_doctor(db, user, doctor_id)
    db.query(models.Prescription).filter(models.Prescription.doctor_id == doctor.id).update(
        {"doctor_id": None}
    )
    db.delete(doctor)
    db.commit()




UPLOAD_DIR = "uploads"
MAX_BYTES = 10 * 1024 * 1024
FILE_SIGNATURES = {
    ".jpg": b"\xff\xd8\xff",
    ".jpeg": b"\xff\xd8\xff",
    ".png": b"\x89PNG\r\n\x1a\n",
    ".pdf": b"%PDF-",
}


def find_prescription(db: Session, user: models.User, prescription_id: int):
    prescription = (
        db.query(models.Prescription)
        .filter(models.Prescription.id == prescription_id, models.Prescription.user_id == user.id)
        .first()
    )
    if prescription is None:
        raise HTTPException(status_code=404, detail="Prescription not found")
    return prescription


@app.post("/prescriptions", response_model=PrescriptionOut, status_code=201)
async def add_prescription(
    prescription_date: date = Form(...),
    doctor_id: Optional[int] = Form(None),
    notes: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if prescription_date > date.today():
        raise HTTPException(status_code=422, detail="Prescription date cannot be in the future")

    if doctor_id is not None:
        find_doctor(db, user, doctor_id)

    saved_path = None
    if file is not None and file.filename:
        extension = os.path.splitext(file.filename)[1].lower()
        signature = FILE_SIGNATURES.get(extension)
        if signature is None:
            raise HTTPException(status_code=400, detail="Upload a JPG, PNG or PDF file")

        data = await file.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise HTTPException(status_code=413, detail="File is larger than 10 MB")
        if not data.startswith(signature):
            raise HTTPException(status_code=400, detail="The file content does not match its type")

        folder = os.path.join(UPLOAD_DIR, str(user.id))
        os.makedirs(folder, exist_ok=True)
        saved_path = os.path.join(folder, uuid.uuid4().hex + extension)
        with open(saved_path, "wb") as f:
            f.write(data)

    prescription = models.Prescription(
        user_id=user.id,
        doctor_id=doctor_id,
        prescription_date=prescription_date,
        notes=notes,
        file_path=saved_path,
    )
    db.add(prescription)
    db.commit()
    db.refresh(prescription)
    return prescription


@app.get("/prescriptions", response_model=list[PrescriptionOut])
def list_prescriptions(
    doctor_id: Optional[int] = None,
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    query = db.query(models.Prescription).filter(models.Prescription.user_id == user.id)
    if doctor_id is not None:
        query = query.filter(models.Prescription.doctor_id == doctor_id)
    return query.order_by(
        models.Prescription.prescription_date.desc(), models.Prescription.id.desc()
    ).all()


@app.get("/prescriptions/{prescription_id}/file")
def get_prescription_file(
    prescription_id: int,
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    prescription = find_prescription(db, user, prescription_id)
    if not prescription.file_path or not os.path.exists(prescription.file_path):
        raise HTTPException(status_code=404, detail="No file for this prescription")
    return FileResponse(prescription.file_path)

@app.delete("/prescriptions/{prescription_id}", status_code=204)
def delete_prescription(
    prescription_id: int,
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    prescription = find_prescription(db, user, prescription_id)
    if prescription.file_path and os.path.exists(prescription.file_path):
        os.remove(prescription.file_path)
    db.query(models.Medicine).filter(models.Medicine.prescription_id == prescription.id).delete()
    db.delete(prescription)
    db.commit()


    

def fill_dates(data: dict, prescription_date: date) -> dict:
    """Start defaults to the prescription date. End is the last day of the course."""
    if data["start_date"] is None:
        data["start_date"] = prescription_date
    if data["end_date"] is None and data["duration_days"] is not None:
        data["end_date"] = data["start_date"] + timedelta(days=data["duration_days"] - 1)
    if data["end_date"] is not None and data["end_date"] < data["start_date"]:
        raise HTTPException(status_code=422, detail="End date cannot be before the start date")
    return data


def find_medicine(db: Session, user: models.User, medicine_id: int):
    medicine = (
        db.query(models.Medicine)
        .filter(models.Medicine.id == medicine_id, models.Medicine.user_id == user.id)
        .first()
    )
    if medicine is None:
        raise HTTPException(status_code=404, detail="Medicine not found")
    return medicine


@app.post(
    "/prescriptions/{prescription_id}/medicines",
    response_model=MedicineOut,
    status_code=201,
)
def add_medicine(
    prescription_id: int,
    body: MedicineIn,
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    prescription = find_prescription(db, user, prescription_id)
    data = fill_dates(body.model_dump(), prescription.prescription_date)

    medicine = models.Medicine(
        user_id=user.id, prescription_id=prescription.id, confirmed=True, **data
    )
    db.add(medicine)
    db.commit()
    db.refresh(medicine)
    return medicine


@app.get("/prescriptions/{prescription_id}/medicines", response_model=list[MedicineOut])
def list_prescription_medicines(
    prescription_id: int,
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    prescription = find_prescription(db, user, prescription_id)
    return (
        db.query(models.Medicine)
        .filter(models.Medicine.prescription_id == prescription.id)
        .order_by(models.Medicine.id)
        .all()
    )


@app.get("/medicines/current", response_model=list[MedicineOut])
def current_medicines(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    """Medicines not finished yet: no end date, or an end date that is today or later."""
    return (
        db.query(models.Medicine)
        .filter(
            models.Medicine.user_id == user.id,
            or_(models.Medicine.end_date.is_(None), models.Medicine.end_date >= date.today()),
        )
        .order_by(models.Medicine.start_date.desc(), models.Medicine.id.desc())
        .all()
    )


@app.put("/medicines/{medicine_id}", response_model=MedicineOut)
def update_medicine(
    medicine_id: int,
    body: MedicineIn,
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    medicine = find_medicine(db, user, medicine_id)
    prescription = find_prescription(db, user, medicine.prescription_id)
    data = fill_dates(body.model_dump(), prescription.prescription_date)

    for key, value in data.items():
        setattr(medicine, key, value)
    db.commit()
    db.refresh(medicine)
    return medicine


@app.delete("/medicines/{medicine_id}", status_code=204)
def delete_medicine(
    medicine_id: int,
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    medicine = find_medicine(db, user, medicine_id)
    db.delete(medicine)
    db.commit()