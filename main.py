import shutil
import uuid
from random import randint
import app
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Query, Body
from sqlalchemy import Boolean, create_engine, Column, Integer, String, ForeignKey, Date, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import qrcode
import os

from bot import send_telegram_message, send_record_telegram
from email_utils import send_appointment_email, send_record_email

tg_codes = {}

from starlette.staticfiles import StaticFiles

QR_CODE_DIR = "qr_codes"
os.makedirs(QR_CODE_DIR, exist_ok=True)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Database setup
DATABASE_URL = "sqlite:///./main1.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class MedicalCenter(Base):
    __tablename__ = "med_centers"

    idCenter = Column(Integer, primary_key=True, autoincrement=True, index=True)
    centerName = Column(String, nullable=False)
    centerDescription = Column(String, nullable=True)
    centerAddress = Column(String, nullable=False)
    centerNumber = Column(String, nullable=False)

    users = relationship("User", back_populates="med_center")
    feedbacks = relationship("Feedback", back_populates="med_center")  # Add this line


class InpatientCare(Base):
    __tablename__ = "inpatient_care"

    id = Column(Integer, primary_key=True, index=True)
    userId = Column(Integer, ForeignKey('users.id'))
    medCenterId = Column(Integer, ForeignKey('med_centers.idCenter'))
    floor = Column(Integer)
    ward = Column(Integer)
    active = Column(String)
    receipt_date = Column(String)  # Можно использовать Date, но для SQLite String проще
    expire_date = Column(String)

    user = relationship("User", back_populates="inpatient_cares")
    med_center = relationship("MedicalCenter")


class Doctor(Base):
    __tablename__ = "doctors"

    userId = Column(Integer, ForeignKey('users.id'), primary_key=True)
    work_type = Column(String)
    experience = Column(String)
    category = Column(String)

    feedbacks = relationship("Feedback", back_populates="doctor")
    user = relationship("User", back_populates="doctor")

class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, index=True)
    userId = Column(Integer, ForeignKey('users.id'))
    doctorId = Column(Integer, ForeignKey('doctors.userId'))
    medCenterId = Column(Integer, ForeignKey('med_centers.idCenter'))  # Fixed typo here
    grade = Column(Integer)
    description = Column(String)
    active = Column(String)

    user = relationship("User", back_populates="feedbacks")
    doctor = relationship("Doctor", back_populates="feedbacks")
    med_center = relationship("MedicalCenter", back_populates="feedbacks")  # Fixed reference here

class QRCode(Base):
    __tablename__ = "qr_codes"
    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    userId = Column(Integer, ForeignKey('users.id'))
    path = Column(String, nullable=False)

    user = relationship("User", back_populates="qr_code")


class Record(Base):
    __tablename__ = "records"

    id = Column(Integer, primary_key=True, index=True)
    userId = Column(Integer, ForeignKey('users.id'))
    doctorId = Column(Integer)
    description = Column(String)
    assignment = Column(String)
    paidOrFree = Column(String)
    price = Column(Integer, nullable=True)
    time_start = Column(String)
    time_end = Column(String)
    medCenterId = Column(Integer, ForeignKey('med_centers.idCenter'))

    med_center = relationship("MedicalCenter")
    photos = relationship("RecordPhoto", back_populates="record")  # Добавлено отношение к фото


class RecordPhoto(Base):
    __tablename__ = "record_photos"

    id = Column(Integer, primary_key=True, index=True)
    record_id = Column(Integer, ForeignKey('records.id'))
    photo_path = Column(String)

    record = relationship("Record", back_populates="photos")

class ReceptionSchedule(Base):
    __tablename__ = "reception_schedule"

    id = Column(Integer, primary_key=True, index=True)
    doctorId = Column(Integer, ForeignKey('doctors.userId'))
    userId = Column(Integer, ForeignKey('users.id'))
    date = Column(String)
    time = Column(String)
    reason = Column(String, nullable=True)
    active = Column(String)

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    key = Column(String, unique=True, index=True)
    role = Column(String)
    medCenterId = Column(Integer, ForeignKey("med_centers.idCenter"))
    fullName = Column(String)
    email = Column(String)
    address = Column(String)
    tgId = Column(Integer)
    education = Column(String)

    inpatient_cares = relationship("InpatientCare", back_populates="user")
    med_center = relationship("MedicalCenter", back_populates="users")
    doctor = relationship(
        "Doctor",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan"
    )
    feedbacks = relationship("Feedback", back_populates="user")  # You already have this
    qr_code = relationship("QRCode", uselist=False, back_populates="user")


Base.metadata.create_all(bind=engine)

app = FastAPI()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.mount("/qr_codes", StaticFiles(directory="qr_codes"), name="qr_codes")


# Pydantic models
class UserCreate(BaseModel):
    key: str
    role: str
    medCenterId: Optional[int] = None
    fullName: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    tgId: Optional[int] = None
    work_type: Optional[str] = None
    experience: Optional[str] = None
    category: Optional[str] = None


class SlotCreate(BaseModel):
    doctorId: int
    date: str
    time: str


class InpatientCareCreate(BaseModel):
    userId: int
    floor: int
    ward: int
    receipt_date: str
    expire_date: str

class InpatientCareResponse(BaseModel):
    id: int
    userId: int
    userFullName: str
    medCenterId: int
    floor: int
    ward: int
    receipt_date: str
    expire_date: str
    active: str

    class Config:
        from_attributes = True

class UserSearchResponse(BaseModel):
    id: int
    fullName: str


class UserResponse(BaseModel):
    id: int
    key: str
    role: str
    medCenterId: Optional[int] = None
    fullName: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    tgId: Optional[int] = None
    centerName: Optional[str] = None
    work_type: Optional[str] = None
    experience: Optional[str] = None
    category: Optional[str] = None
    education: Optional[str] = None

    class Config:
        from_attributes = True  # Update from orm_mode to from_attributes for Pydantic v2


class LicenseKeyRequest(BaseModel):
    key: str


class LoginResponse(BaseModel):
    role: str
    userId: int
    medCenterId: Optional[int]
    full_name: str
    center_name: Optional[str]

    class RejectReason(BaseModel):
        reason: str

    class FeedbackResponse(BaseModel):
        id: int
        userId: int
        doctorId: int
        medCenterId: int
        grade: int
        description: str
        active: str
        reason: Optional[str] = None

    class MedicalCenterCreate(BaseModel):
        idCenter: int
        centerName: str
        centerDescription: Optional[str] = None
        centerAddress: str
        centerNumber: str

    class MedicalCenterResponse(BaseModel):
        idCenter: int
        centerName: str
        centerDescription: Optional[str]
        centerAddress: str
        centerNumber: str

    @app.post("/tg-bind/start")
    def tg_bind_start(user_id: int):
        code = str(randint(1000, 9999))
        # Можно временно хранить код в памяти, если нужно (например, в dict), но в базе не сохраняем!
        # Например, можно использовать глобальный dict (НЕ для продакшена!):
        global tg_codes
        tg_codes[code] = user_id
        return {"code": code}

    @app.get("/users/{user_id}/tg-id")
    def get_user_tg_id(user_id: int, db: Session = Depends(get_db)):
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return {"tgId": user.tgId}

    class TgUnlinkRequest(BaseModel):
        user_id: int

    @app.post("/tg-bind/unlink")
    def tg_unlink(request: TgUnlinkRequest, db: Session = Depends(get_db)):
        user = db.query(User).filter(User.id == request.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user.tgId = None
        db.commit()
        return {"message": "Telegram аккаунт отвязан"}

    @app.post("/tg-bind/confirm")
    def tg_bind_confirm(code: str = Body(...), tg_id: int = Body(...), db: Session = Depends(get_db)):
        user_id = tg_codes.get(code)
        if not user_id:
            raise HTTPException(status_code=404, detail="Code not found or expired")
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user.tgId = tg_id
        db.commit()
        # После успешной привязки удаляем код
        del tg_codes[code]
        return {"message": f"Аккаунт {user.fullName} успешно привязан"}

    @app.post("/med-centers", response_model=MedicalCenterResponse)
    def create_medical_center(center: MedicalCenterCreate, db: Session = Depends(get_db)):
        db_center = MedicalCenter(**center.dict())
        db.add(db_center)
        db.commit()
        db.refresh(db_center)
        return db_center

    @app.delete("/med-centers/{center_id}")
    def delete_medical_center(center_id: int, db: Session = Depends(get_db)):
        center = db.query(MedicalCenter).filter(MedicalCenter.idCenter == center_id).first()
        if not center:
            raise HTTPException(status_code=404, detail="Medical center not found")

        db.delete(center)
        db.commit()
        return {"message": "Medical center deleted successfully"}

    @app.get("/inpatient-cares", response_model=List[InpatientCareResponse])
    def get_inpatient_cares(med_center_id: int, active: str = "true", db: Session = Depends(get_db)):
        cares = db.query(InpatientCare).filter(
            InpatientCare.medCenterId == med_center_id,
            InpatientCare.active == active
        ).all()

        result = []
        for care in cares:
            user = db.query(User).filter(User.id == care.userId).first()
            result.append(InpatientCareResponse(
                id=care.id,
                userId=care.userId,
                userFullName=user.fullName if user else "Unknown",
                medCenterId=care.medCenterId,
                floor=care.floor,
                ward=care.ward,
                receipt_date=str(care.receipt_date) if care.receipt_date else "",
                expire_date=str(care.expire_date) if care.expire_date else "",
                active=care.active  # Теперь точно передаётся
            ))
        return result

    @app.get("/debug/qr-codes")
    def debug_qr_codes(db: Session = Depends(get_db)):
        return db.query(QRCode).all()

    @app.patch("/users/{user_id}/education")
    def update_education(user_id: int, db: Session = Depends(get_db)):
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user.education = "true"
        db.commit()
        return {"message": "Education updated"}

    @app.post("/reception-schedule/batch")
    def create_slots(slots: List[SlotCreate], db: Session = Depends(get_db)):
        for slot in slots:
            new_slot = ReceptionSchedule(
                doctorId=slot.doctorId,
                userId=None,
                date=slot.date,
                time=slot.time,
                reason=None,
                active="false"
            )
            db.add(new_slot)
        db.commit()
        return {"message": "Slots created"}

    @app.post("/inpatient-cares")
    def create_inpatient_care(care: InpatientCareCreate, med_center_id: int, db: Session = Depends(get_db)):
        db_care = InpatientCare(
            **care.dict(),
            medCenterId=med_center_id,
            active="true"
        )
        db.add(db_care)
        db.commit()
        db.refresh(db_care)
        return db_care

    @app.get("/doctor/appointments/range")
    def get_doctor_appointments_range(
            doctorId: int,
            start_date: str,
            end_date: str,
            db: Session = Depends(get_db)
    ):
        query = db.query(ReceptionSchedule).filter(
            ReceptionSchedule.doctorId == doctorId,
            ReceptionSchedule.date >= start_date,
            ReceptionSchedule.date <= end_date
        )

        appointments = query.all()

        result = []
        for app in appointments:
            user = db.query(User).filter(User.id == app.userId).first() if app.userId else None
            result.append({
                "id": app.id,
                "userId": app.userId if app.userId else 0,
                "fullName": user.fullName if user else "Неизвестный пациент",
                "date": app.date,
                "time": app.time,
                "reason": app.reason,
                "active": app.active
            })

        return result

    @app.get("/doctor/appointments")
    def get_doctor_appointments(
            doctorId: int,
            date: str,
            active: Optional[str] = None,
            db: Session = Depends(get_db)
    ):
        query = db.query(ReceptionSchedule).filter(
            ReceptionSchedule.doctorId == doctorId,
            ReceptionSchedule.date == date
        )

        if active is not None:
            query = query.filter(ReceptionSchedule.active == active)

        appointments = query.all()

        result = []
        for app in appointments:
            user = db.query(User).filter(User.id == app.userId).first() if app.userId else None
            result.append({
                "id": app.id,
                "userId": app.userId,
                "fullName": user.fullName if user else "Неизвестный пациент",
                "date": app.date,  # <-- добавь это!
                "time": app.time,
                "reason": app.reason,
                "active": app.active
            })

        return result


    @app.get("/users/{user_id}/qrcode")
    def get_qrcode(user_id: int, db: Session = Depends(get_db)):
        qrcode = db.query(QRCode).filter(QRCode.userId == user_id).first()
        if not qrcode:
            raise HTTPException(status_code=404, detail="QR code not found")
        return qrcode

    @app.get("/med-centers/{center_id}/doctors/average-rating")
    def get_average_doctor_rating(center_id: int, db: Session = Depends(get_db)):
        # Получаем всех врачей медцентра
        doctors = db.query(Doctor).join(User).filter(User.medCenterId == center_id).all()
        if not doctors:
            return {"average_rating": None}
        doctor_ids = [doc.userId for doc in doctors]
        # Получаем все отзывы по этим врачам
        feedbacks = db.query(Feedback).filter(Feedback.doctorId.in_(doctor_ids), Feedback.active == "true").all()
        if not feedbacks:
            return {"average_rating": None}
        avg = sum(f.grade for f in feedbacks) / len(feedbacks)
        return {"average_rating": round(avg, 2)}


    @app.patch("/inpatient-cares/{care_id}")
    def update_inpatient_care(care_id: int, active: str, db: Session = Depends(get_db)):
        care = db.query(InpatientCare).filter(InpatientCare.id == care_id).first()
        if not care:
            raise HTTPException(status_code=404, detail="Care record not found")

        care.active = active
        if active == "false":
            # Текущее время в миллисекундах
            care.expire_date = str(int(datetime.utcnow().timestamp() * 1000))

        db.commit()
        return {"message": "Care record updated"}

    @app.get("/users/search")
    def search_users(med_center_id: int, query: str, db: Session = Depends(get_db)):
        users = db.query(User).filter(
            User.medCenterId == med_center_id,
            User.fullName.ilike(f"%{query}%")
        ).all()
        return [{"id": u.id, "fullName": u.fullName, "role": u.role} for u in users]

    @app.get("/feedbacks", response_model=List[FeedbackResponse])
    def get_feedbacks(db: Session = Depends(get_db)):
        return db.query(Feedback).all()

    @app.post("/feedbacks/{feedback_id}/approve")
    def approve_feedback(feedback_id: int, db: Session = Depends(get_db)):
        feedback = db.query(Feedback).filter(Feedback.id == feedback_id).first()
        if not feedback:
            raise HTTPException(status_code=404, detail="Feedback not found")

        feedback.active = "true"
        db.commit()
        return {"message": "Feedback approved"}

    @app.post("/feedbacks/{feedback_id}/reject")
    def reject_feedback(feedback_id: int, reason: RejectReason, db: Session = Depends(get_db)):
        feedback = db.query(Feedback).filter(Feedback.id == feedback_id).first()
        if not feedback:
            raise HTTPException(status_code=404, detail="Feedback not found")

        feedback.active = "false"
        feedback.reason = reason.reason
        db.commit()
        return {"message": "Feedback rejected"}

class MedicalCenterResponse(BaseModel):
        idCenter: int
        centerName: str
        centerDescription: Optional[str]
        centerAddress: str
        centerNumber: str

@app.get("/med-centers", response_model=List[MedicalCenterResponse])
def get_medical_centers(db: Session = Depends(get_db)):
    centers = db.query(MedicalCenter).all()
    return centers

class MedicalCenterUpdate(BaseModel):
    centerName: Optional[str] = None
    centerDescription: Optional[str] = None
    centerAddress: Optional[str] = None
    centerNumber: Optional[str] = None


class RecordPhotoCreate(BaseModel):
    photo_path: str


class RecordPhotoResponse(BaseModel):
    id: int
    photo_path: str

    class Config:
        from_attributes = True


class RecordCreate(BaseModel):
    userId: int
    doctorId: int
    description: str
    assignment: str
    paidOrFree: str
    price: Optional[int] = None
    time_start: str
    time_end: str
    medCenterId: int
    photos: List[str] = []  # Список путей к фото


class RecordResponse(BaseModel):
    id: int
    userId: int
    doctorId: int
    doctorFullName: Optional[str] = None
    doctorWorkType: Optional[str] = None
    description: str
    assignment: str
    paidOrFree: str
    price: Optional[int] = None
    time_start: str
    time_end: str
    medCenterId: int
    photos: List[RecordPhotoResponse] = []

    class Config:
        from_attributes = True

@app.get("/doctors/{doctor_id}/free-slots")
def get_free_slots(doctor_id: int, db: Session = Depends(get_db)):
    today = datetime.now().strftime("%d.%m.%Y")
    slots = db.query(ReceptionSchedule).filter(
        ReceptionSchedule.doctorId == doctor_id,
        ReceptionSchedule.date >= today,
        ReceptionSchedule.userId == None
    ).all()
    return [
        {
            "id": slot.id,
            "date": slot.date,
            "time": slot.time,
            "userId": slot.userId,
            "reason": slot.reason
        }
        for slot in slots
    ]

class DoctorInfoResponse(BaseModel):
    work_type: Optional[str] = None
    category: Optional[str] = None

@app.get("/doctors/{doctor_id}/info", response_model=DoctorInfoResponse)
def get_doctor_info(doctor_id: int, db: Session = Depends(get_db)):
    doctor = db.query(Doctor).filter(Doctor.userId == doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
    return DoctorInfoResponse(
        work_type=doctor.work_type,
        category=doctor.category
    )

@app.get("/records/patient/{user_id}", response_model=List[RecordResponse])
def get_patient_records(user_id: int, db: Session = Depends(get_db)):
    records = db.query(Record).filter(Record.userId == user_id).all()

    result = []
    for record in records:
        photos = db.query(RecordPhoto).filter(RecordPhoto.record_id == record.id).all()
        # Получаем ФИО врача
        doctor_user = db.query(User).filter(User.id == record.doctorId).first()
        doctor_full_name = doctor_user.fullName if doctor_user else "Неизвестно"
        # Получаем специализацию врача
        doctor = db.query(Doctor).filter(Doctor.userId == record.doctorId).first()
        doctor_work_type = doctor.work_type if doctor else "Неизвестно"

        result.append(RecordResponse(
            id=record.id,
            userId=record.userId,
            doctorId=record.doctorId,
            doctorFullName=doctor_full_name,
            doctorWorkType=doctor_work_type,
            description=record.description,
            assignment=record.assignment,
            paidOrFree=record.paidOrFree,
            price=record.price,
            time_start=record.time_start,
            time_end=record.time_end,
            medCenterId=record.medCenterId,
            photos=[RecordPhotoResponse(
                id=photo.id,
                photo_path=photo.photo_path
            ) for photo in photos]
        ))

    return result

@app.get("/records/user/{user_id}", response_model=List[RecordResponse])
def get_user_records(user_id: int, db: Session = Depends(get_db)):
    records = db.query(Record).filter(Record.userId == user_id).all()

    if not records:
        raise HTTPException(status_code=404, detail="No records found for this user")

    return records

class RecordCompleteNotifyRequest(BaseModel):
    user_id: int
    doctor_id: int
    description: str
    assignment: str
    paid_or_free: str
    price: Optional[int] = None
    date: str
    time: str
    photo_urls: List[str]

@app.post("/notify/record-complete")
def notify_record_complete(body: RecordCompleteNotifyRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == body.user_id).first()
    doctor = db.query(User).filter(User.id == body.doctor_id).first()
    doctor_info = db.query(Doctor).filter(Doctor.userId == body.doctor_id).first()

    patient_name = user.fullName if user else "Неизвестно"
    doctor_name = doctor.fullName if doctor else "Неизвестно"
    doctor_specialization = doctor_info.work_type if doctor_info else "Неизвестно"

    # Email
    if user and user.email:
        send_record_email(
            to_email=user.email,
            patient_name=patient_name,
            doctor_name=doctor_name,
            doctor_specialization=doctor_specialization,
            date=body.date,
            time=body.time,
            description=body.description,
            assignment=body.assignment,
            paid_or_free=body.paid_or_free,
            price=body.price,
            photo_urls=body.photo_urls
        )
    # Telegram
    if user and user.tgId:
        send_record_telegram(
            tg_id=user.tgId,
            patient_name=patient_name,
            doctor_name=doctor_name,
            doctor_specialization=doctor_specialization,
            date=body.date,
            time=body.time,
            description=body.description,
            assignment=body.assignment,
            paid_or_free=body.paid_or_free,
            price=body.price,
            photo_urls=body.photo_urls
        )
    return {"message": "Уведомления отправлены"}

@app.get("/stats/appointments-today")
def get_appointments_today(
    med_center_id: int = Query(...),
    db: Session = Depends(get_db)
):
    today = datetime.now().strftime("%Y-%m-%d")
    count = db.query(Record).filter(
        Record.medCenterId == med_center_id,
        Record.time_end.startswith(today)
    ).count()
    return {"count": count}

@app.get("/stats/doctors-count")
def get_doctors_count(
    med_center_id: int = Query(...),
    db: Session = Depends(get_db)
):
    count = db.query(User).filter(
        User.role == "doctor",
        User.medCenterId == med_center_id
    ).count()
    return {"count": count}

@app.get("/stats/inpatient-patients-count")
def get_inpatient_patients_count(
    med_center_id: int = Query(...),
    db: Session = Depends(get_db)
):
    count = db.query(InpatientCare).filter(
        InpatientCare.medCenterId == med_center_id,
        InpatientCare.active == "true"
    ).count()
    return {"count": count}

@app.post("/records")
async def create_record(record: RecordCreate, db: Session = Depends(get_db)):
    # Создаем запись
    db_record = Record(
        userId=record.userId,
        doctorId=record.doctorId,
        description=record.description,
        assignment=record.assignment,
        paidOrFree=record.paidOrFree,
        price=record.price,
        time_start=record.time_start,
        time_end=record.time_end,
        medCenterId=record.medCenterId
    )
    db.add(db_record)
    db.commit()
    db.refresh(db_record)

    # Добавляем фото
    for photo_path in record.photos:
        db_photo = RecordPhoto(record_id=db_record.id, photo_path=photo_path)
        db.add(db_photo)

    db.commit()
    return db_record

@app.get("/stats/average-appointment-time")
def get_average_appointment_time(med_center_id: int, db: Session = Depends(get_db)):
    today = datetime.now().strftime("%Y-%m-%d")
    records = db.query(Record).filter(
        Record.medCenterId == med_center_id,
        Record.time_end.startswith(today)
    ).all()
    total_seconds = 0
    count = 0
    for r in records:
        if r.time_start and r.time_end:
            try:
                t1 = datetime.strptime(r.time_start, "%Y-%m-%d %H:%M:%S")
                t2 = datetime.strptime(r.time_end, "%Y-%m-%d %H:%M:%S")
                diff = (t2 - t1).total_seconds()
                if diff > 0:
                    total_seconds += diff
                    count += 1
            except Exception:
                continue
    avg_minutes = round(total_seconds / 60 / count, 1) if count else 0
    return {"average_time_minutes": avg_minutes}

@app.get("/stats/income-today")
def get_income_today(med_center_id: int, db: Session = Depends(get_db)):
    today = datetime.now().strftime("%Y-%m-%d")
    records = db.query(Record).filter(
        Record.medCenterId == med_center_id,
        Record.time_end.startswith(today)
    ).all()
    total = sum(r.price or 0 for r in records)
    return {"income": total}

@app.get("/stats/paid-free-counts")
def get_paid_free_counts(med_center_id: int, db: Session = Depends(get_db)):
    today = datetime.now().strftime("%Y-%m-%d")
    records = db.query(Record).filter(
        Record.medCenterId == med_center_id,
        Record.time_end.startswith(today)
    ).all()
    paid = sum(1 for r in records if r.paidOrFree == "payed")
    free = sum(1 for r in records if r.paidOrFree == "free")
    return {"paid": paid, "free": free}

@app.get("/stats/feedbacks-in-progress")
def get_feedbacks_in_progress(med_center_id: int, db: Session = Depends(get_db)):
    count = db.query(Feedback).filter(
        Feedback.medCenterId == med_center_id,
        Feedback.active == "in_progress"
    ).count()
    return {"count": count}

@app.get("/stats/feedbacks-week")
def get_feedbacks_week(med_center_id: int, db: Session = Depends(get_db)):
    today = datetime.now()
    week_ago = today - timedelta(days=7)
    count = db.query(Feedback).filter(
        Feedback.medCenterId == med_center_id,
        Feedback.active == "true"
    ).count()
    return {"count": count}

@app.post("/records/upload-photos")
async def upload_photos(files: List[UploadFile] = File(...)):
    uploaded_paths = []
    for file in files:
        try:
            file_ext = os.path.splitext(file.filename)[1]
            unique_filename = f"{uuid.uuid4()}{file_ext}"
            file_path = os.path.join(UPLOAD_DIR, unique_filename)

            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            uploaded_paths.append(f"/uploads/{unique_filename}")  # Измените путь здесь
        except Exception as e:
            continue

    return {"paths": uploaded_paths}

class FeedbackCreate(BaseModel):
    userId: int
    doctorId: int
    medCenterId: int
    grade: int
    description: str
    active: str = "in_progress"

@app.post("/feedbacks", response_model=FeedbackCreate)
def create_feedback(feedback: FeedbackCreate, db: Session = Depends(get_db)):

    db_feedback = Feedback(
        userId=feedback.userId,
        doctorId=feedback.doctorId,
        medCenterId=feedback.medCenterId,
        grade=feedback.grade,
        description=feedback.description,
        active=feedback.active
    )
    db.add(db_feedback)
    db.commit()
    db.refresh(db_feedback)
    return feedback

@app.get("/med-centers/with-rating")
def get_med_centers_with_rating(db: Session = Depends(get_db)):
    centers = db.query(MedicalCenter).all()
    result = []
    for center in centers:
        # Получаем всех врачей центра
        doctors = db.query(Doctor).join(User).filter(User.medCenterId == center.idCenter).all()
        doctor_ids = [doc.userId for doc in doctors]
        # Получаем отзывы по этим врачам
        feedbacks = db.query(Feedback).filter(Feedback.doctorId.in_(doctor_ids), Feedback.active == "true").all()
        avg_rating = round(sum(f.grade for f in feedbacks) / len(feedbacks), 2) if feedbacks else None
        result.append({
            "idCenter": center.idCenter,
            "centerName": center.centerName,
            "centerAddress": center.centerAddress,
            "centerNumber": center.centerNumber,
            "average_rating": avg_rating
        })
    return result

@app.get("/med-centers/{center_id}/doctors/with-rating")
def get_doctors_with_rating(center_id: int, db: Session = Depends(get_db)):
    doctors = db.query(Doctor).join(User).filter(User.medCenterId == center_id).all()
    result = []
    for doc in doctors:
        feedbacks = db.query(Feedback).filter(Feedback.doctorId == doc.userId, Feedback.active == "true").all()
        avg_rating = round(sum(f.grade for f in feedbacks) / len(feedbacks), 2) if feedbacks else None
        user = db.query(User).filter(User.id == doc.userId).first()
        result.append({
            "doctorId": doc.userId,
            "fullName": user.fullName if user else "",
            "work_type": doc.work_type,
            "category": doc.category,
            "average_rating": avg_rating
        })
    return result

@app.get("/doctors/{doctor_id}/feedbacks")
def get_doctor_feedbacks(doctor_id: int, db: Session = Depends(get_db)):
    feedbacks = db.query(Feedback).filter(Feedback.doctorId == doctor_id, Feedback.active == "true").all()
    result = []
    for fb in feedbacks:
        user = db.query(User).filter(User.id == fb.userId).first()
        result.append({
            "id": fb.id,
            "grade": fb.grade,
            "description": fb.description,
            "userFullName": user.fullName if user else "Аноним"
        })
    return result

@app.patch("/appointments/{app_id}")
def update_appointment_status(
    app_id: int,
    active: str,
    userId: Optional[int] = Query(None),
    reason: Optional[str] = Query(None),
    clear_data: bool = False,
    db: Session = Depends(get_db)
):
    appointment = db.query(ReceptionSchedule).filter(ReceptionSchedule.id == app_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    appointment.active = active

    if userId is not None:
        appointment.userId = userId

    if reason is not None:
        appointment.reason = reason

    if clear_data:
        appointment.userId = None
        appointment.reason = None

    db.commit()

    # --- ДОБАВЬ ЭТО ---
    if active == "true" and userId is not None:
        user = db.query(User).filter(User.id == userId).first()
        doctor = db.query(User).filter(User.id == appointment.doctorId).first()
        doctor_info = db.query(Doctor).filter(Doctor.userId == appointment.doctorId).first()
        if user and user.email:
            send_appointment_email(
                to_email=user.email,
                doctor_name=doctor.fullName if doctor else "Неизвестно",
                doctor_specialization=doctor_info.work_type if doctor_info else "Неизвестно",
                date=appointment.date,
                time=appointment.time
            )
        if user and user.tgId:
            text = (
                f"Вы записались к врачу!\n\n"
                f"Врач: {doctor.fullName if doctor else 'Неизвестно'}\n"
                f"Специализация: {doctor_info.work_type if doctor_info else 'Неизвестно'}\n"
                f"Дата: {appointment.date}\n"
                f"Время: {appointment.time}"
            )
            send_telegram_message(user.tgId, text)
    # --- КОНЕЦ ДОБАВЛЕНИЯ ---

    return {"message": "Appointment updated"}

@app.delete("/appointments/{app_id}")
def delete_appointment(app_id: int, db: Session = Depends(get_db)):
    appointment = db.query(ReceptionSchedule).filter(ReceptionSchedule.id == app_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    db.delete(appointment)
    db.commit()
    return {"message": "Appointment deleted successfully"}

@app.post("/appointments")
def create_appointment(
        doctorId: int,
        userId: Optional[int] = None,
        date: str = ...,
        time: str = ...,
        reason: Optional[str] = None,
        db: Session = Depends(get_db)
):
    # Проверяем существование врача
    db_doctor = db.query(User).filter(User.id == doctorId).first()
    if not db_doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    # Проверяем пользователя только если userId задан и не 0
    if userId and userId != 0:
        db_user = db.query(User).filter(User.id == userId).first()
        if not db_user:
            raise HTTPException(status_code=404, detail="User not found")
    else:
        userId = None

    new_appointment = ReceptionSchedule(
        doctorId=doctorId,
        userId=userId,
        date=date,
        time=time,
        reason=reason,
        active="true" if userId else "false"
    )

    db.add(new_appointment)
    db.commit()
    db.refresh(new_appointment)

    return {"message": "Appointment created successfully"}

@app.put("/med-centers/{center_id}", response_model=MedicalCenterResponse)
def update_medical_center(
    center_id: int,
    center_update: MedicalCenterUpdate,
    db: Session = Depends(get_db)
):
    db_center = db.query(MedicalCenter).filter(MedicalCenter.idCenter == center_id).first()
    if not db_center:
        raise HTTPException(status_code=404, detail="Medical center not found")

    update_data = center_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_center, key, value)

    db.commit()
    db.refresh(db_center)
    return db_center

@app.post("/login-with-key", response_model=LoginResponse)
def login_with_key(request: LicenseKeyRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.key == request.key).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    center_name = user.med_center.centerName if user.med_center else None

    return LoginResponse(
        role=user.role,
        userId=user.id,
        medCenterId=user.medCenterId,
        full_name=user.fullName if user.fullName else "",
        center_name=center_name
    )


@app.get("/users", response_model=List[UserResponse])
def get_users(db: Session = Depends(get_db)):
    users = db.query(User).filter(User.role != 'sudo-admin').all()
    user_responses = []
    for user in users:
        doctor = None
        if user.role == "doctor":
            doctor = db.query(Doctor).filter(Doctor.userId == user.id).first()
        user_responses.append(
            UserResponse(
                id=user.id,
                key=user.key,
                role=user.role,
                medCenterId=user.medCenterId,
                fullName=user.fullName,
                email=user.email,
                address=user.address,
                tgId=user.tgId,
                centerName=user.med_center.centerName if user.med_center else None,
                work_type=doctor.work_type if doctor else None,
                experience=doctor.experience if doctor else None,
                category=doctor.category if doctor else None,
                education=user.education
            )
        )
    return user_responses


@app.post("/users", response_model=UserResponse)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    db_user = User(
        key=user.key,
        role=user.role,
        medCenterId=user.medCenterId,
        fullName=user.fullName,
        email=user.email,
        address=user.address,
        tgId=user.tgId,
        education="false"
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    # Если это врач, добавляем в doctors
    if user.role == "doctor":
        db_doctor = Doctor(
            userId=db_user.id,
            work_type=user.work_type,
            experience=user.experience,
            category=user.category
        )
        db.add(db_doctor)
        db.commit()

    # Генерация QR-кода только для ролей, отличных от 'sudo-admin'
    if user.role != 'sudo-admin':
        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr_data = f"UserID:{db_user.id}|Key:{db_user.key}"
            qr.add_data(qr_data)
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")
            qr_filename = f"user_{db_user.id}_qr.png"
            qr_path = os.path.join(QR_CODE_DIR, qr_filename)
            img.save(qr_path)
            db_path = f"/{QR_CODE_DIR}/{qr_filename}"

            qr_code = QRCode(userId=db_user.id, path=db_path)
            db.add(qr_code)
            db.commit()
        except Exception as e:
            print(f"Error generating QR code: {str(e)}")

    center_name = None
    if db_user.medCenterId:
        center = db.query(MedicalCenter).filter(MedicalCenter.idCenter == db_user.medCenterId).first()
        center_name = center.centerName if center else None

    return UserResponse(
        id=db_user.id,
        key=db_user.key,
        role=db_user.role,
        medCenterId=db_user.medCenterId,
        fullName=db_user.fullName,
        email=db_user.email,
        address=db_user.address,
        tgId=db_user.tgId,
        centerName=center_name
    )


@app.put("/users/{user_id}", response_model=UserResponse)
def update_user(user_id: int, user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    for key, value in user.dict().items():
        setattr(db_user, key, value)

    db.commit()
    db.refresh(db_user)
    return db_user


@app.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Удаляем QR-код, если есть
    qr_code = db.query(QRCode).filter(QRCode.userId == user_id).first()
    if qr_code:
        # Удаляем файл QR-кода с диска
        if qr_code.path and os.path.exists(qr_code.path):
            try:
                os.remove(qr_code.path)
            except Exception as e:
                print(f"Error deleting QR code file: {e}")
        db.delete(qr_code)

    db.delete(db_user)
    db.commit()
    return {"message": "User and QR code deleted successfully"}