from datetime import date
from typing import Literal, Optional

# from pydantic import BaseModel, EmailStr, Field, model_validator
# from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator
from pydantic import BaseModel, ConfigDict, EmailStr, Field, computed_field, model_validator


class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)


class UserOut(BaseModel):
    id: int
    email: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ProfileIn(BaseModel):
    full_name: str = Field(min_length=1)
    age: Optional[int] = Field(default=None, ge=0, le=130)
    sex: Optional[Literal["female", "male", "other"]] = None
    blood_group: Optional[Literal["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]] = None
    is_pregnant: Optional[bool] = None
    kidney_egfr: Optional[float] = Field(default=None, ge=0, le=200)
    liver_note: Optional[str] = None


class ProfileOut(ProfileIn):
    id: int


class ConditionIn(BaseModel):
    name: str = Field(min_length=1)
    severity: Optional[Literal["mild", "moderate", "severe"]] = None
    acuity_type: Literal["acute", "chronic"]
    status: Literal["ongoing", "resolved"] = "ongoing"
    diagnosed_date: Optional[date] = None
    resolved_date: Optional[date] = None

    @model_validator(mode="after")
    def check_dates(self):
        if self.status == "ongoing" and self.resolved_date is not None:
            raise ValueError("An ongoing illness cannot have a resolved date")
        if self.diagnosed_date and self.resolved_date and self.resolved_date < self.diagnosed_date:
            raise ValueError("Resolved date cannot be before the diagnosed date")
        return self


class ConditionOut(ConditionIn):
    id: int



class AllergyIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    substance: str = Field(min_length=1)
    reaction: Optional[str] = None
    severity: Optional[Literal["mild", "moderate", "severe"]] = None


class AllergyOut(AllergyIn):
    id: int



class LabIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    test_name: str = Field(min_length=1)
    value: float = Field(allow_inf_nan=False)
    unit: Optional[str] = None
    taken_on: date
    reference_low: Optional[float] = Field(default=None, allow_inf_nan=False)
    reference_high: Optional[float] = Field(default=None, allow_inf_nan=False)

    @model_validator(mode="after")
    def check_values(self):
        if self.taken_on > date.today():
            raise ValueError("Test date cannot be in the future")
        if (
            self.reference_low is not None
            and self.reference_high is not None
            and self.reference_low > self.reference_high
        ):
            raise ValueError("The normal range is the wrong way round")
        return self


class LabOut(LabIn):
    id: int

    @computed_field
    @property
    def flag(self) -> Optional[Literal["low", "normal", "high"]]:
        if self.reference_low is not None and self.value < self.reference_low:
            return "low"
        if self.reference_high is not None and self.value > self.reference_high:
            return "high"
        if self.reference_low is not None or self.reference_high is not None:
            return "normal"
        return None



class DoctorIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1)
    speciality: Optional[str] = None
    clinic: Optional[str] = None
    phone: Optional[str] = Field(default=None, pattern=r"^[0-9+\-\s()]{7,20}$")


class DoctorOut(DoctorIn):
    id: int

    

class PrescriptionOut(BaseModel):
    id: int
    doctor_id: Optional[int] = None
    prescription_date: date
    notes: Optional[str] = None
    file_path: Optional[str] = Field(default=None, exclude=True)

    @computed_field
    @property
    def has_file(self) -> bool:
        return self.file_path is not None


    

class MedicineIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1)
    strength: Optional[str] = None
    dose: Optional[str] = None
    frequency: Optional[str] = None
    duration_days: Optional[int] = Field(default=None, ge=1, le=3650)
    start_date: Optional[date] = None
    end_date: Optional[date] = None

    @model_validator(mode="after")
    def check_dates(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("End date cannot be before the start date")
        return self


class MedicineOut(MedicineIn):
    id: int
    prescription_id: int
    salt_name: Optional[str] = None
    half_life_hours: Optional[float] = None
    confirmed: bool