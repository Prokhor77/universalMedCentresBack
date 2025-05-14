from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import Boolean, create_engine, Column, Integer, String, ForeignKey, Date
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from pydantic import BaseModel
from typing import Optional, List
import qrcode
import os

QR_CODE_DIR = "qr_codes"
os.makedirs(QR_CODE_DIR, exist_ok=True)

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

    id = Column(Integer, primary_key=True, index=True)
    userId = Column(Integer, ForeignKey('users.id'))
    path = Column(String, nullable=False)

    user = relationship("User", back_populates="qr_code")

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
    photo = Column(String)

    inpatient_cares = relationship("InpatientCare", back_populates="user")
    med_center = relationship("MedicalCenter", back_populates="users")
    doctor = relationship("Doctor", back_populates="user", uselist=False)  # Add this line
    feedbacks = relationship("Feedback", back_populates="user")  # You already have this
    qr_code = relationship("QRCode", uselist=False, back_populates="user")


Base.metadata.create_all(bind=engine)

app = FastAPI()



# Pydantic models
class UserCreate(BaseModel):
    key: str
    role: str
    medCenterId: Optional[int] = None
    fullName: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    tgId: Optional[int] = None

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
    centerName: Optional[str] = None  # Make this explicitly optional

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


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class MedicalCenterResponse(BaseModel):
    idCenter: int
    centerName: str
    centerDescription: Optional[str]
    centerAddress: str
    centerNumber: str

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
        return [{"id": u.id, "fullName": u.fullName} for u in users]

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

@app.get("/med-centers", response_model=List[MedicalCenterResponse])
def get_medical_centers(db: Session = Depends(get_db)):
    centers = db.query(MedicalCenter).all()
    return centers



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
    # Добавляем фильтр для исключения пользователей с ролью 'sudo-admin'
    users = db.query(User).filter(User.role != 'sudo-admin').all()

    user_responses = [
        UserResponse(
            id=user.id,
            key=user.key,
            role=user.role,
            medCenterId=user.medCenterId,
            fullName=user.fullName,
            email=user.email,
            address=user.address,
            tgId=user.tgId,
            centerName=user.med_center.centerName if user.med_center else None
        )
        for user in users
    ]
    return user_responses


@app.post("/users", response_model=UserResponse)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    db_user = User(**user.dict())
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

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

            qr_code = QRCode(userId=db_user.id, path=qr_path)
            db.add(qr_code)
            db.commit()
        except Exception as e:
            print(f"Error generating QR code: {str(e)}")

    # Получение информации о медицинском центре
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

    db.delete(db_user)
    db.commit()
    return {"message": "User deleted successfully"}