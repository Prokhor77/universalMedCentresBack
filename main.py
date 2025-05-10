from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey
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

    med_center = relationship("MedicalCenter", back_populates="users")
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