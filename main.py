from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from typing import List, Optional

# Подключение к локальной базе данных SQLite
DATABASE_URL = "sqlite:///./main.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Таблица медцентров
class MedCentre(Base):
    __tablename__ = "med_centres"
    id_center = Column(Integer, primary_key=True, index=True, autoincrement=True)
    center_name = Column(String, nullable=False)
    center_description = Column(String, nullable=False)
    center_address = Column(String, nullable=False)
    center_number = Column(Integer, nullable=False)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)
    med_center_id = Column(Integer, ForeignKey("med_centres.id_center"), nullable=False)
    full_name = Column(String, nullable=False)
    role = Column(String, nullable=False)
    address = Column(String, nullable=False)

# Создание таблиц
Base.metadata.create_all(bind=engine)

# Модель для запроса аутентификации
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class LoginResponse(BaseModel):
  role: str
  med_center_id: Optional[int] = None
  full_name: Optional[str] = None
  center_name: Optional[str] = None


class MedCentreResponse(BaseModel):
    id_center: int
    center_name: str
    center_description: str
    center_address: str
    center_number: int

    class Config:
        orm_mode = True

# Модель для ответа с информацией о главном враче
class MainDoctorResponse(BaseModel):
    id: int
    full_name: str
    email: str
    password: str
    center_name: str
    med_center_id: int
    address: str  # Добавлено поле address

    class Config:
        orm_mode = True

# Модель для поликлиник
class PolyclinicResponse(BaseModel):
    id_center: int
    center_name: str

# Модель для поликлиник
class MedCenResponse(BaseModel):
    id_center: int
    center_name: str
    center_description: str
    center_address: str
    center_number: int


app = FastAPI()

# Функция для получения сессии базы данных
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_user(db: Session, email: str, password: str):
    return db.query(User).filter(User.email == email, User.password == password).first()


@app.post("/login", response_model=LoginResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    print(request.dict())
    user = get_user(db, request.email, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="Неверный email или пароль")

    # Получаем название медицинского центра, если он существует
    med_center = db.query(MedCentre).filter(MedCentre.id_center == user.med_center_id).first()
    center_name = med_center.center_name if med_center else None

    # Проверяем, есть ли med_center_id у пользователя
    med_center_id = user.med_center_id if user.med_center_id else None

    return {
        "role": user.role,
        "med_center_id": med_center_id,  # Возвращаем med_center_id или None
        "full_name": user.full_name,
        "center_name": center_name
    }

@app.get("/main-doctors", response_model=List[MainDoctorResponse])
def get_main_doctors(db: Session = Depends(get_db)):
    doctors = (
        db.query(User.id, User.full_name, User.email, User.password, MedCentre.center_name, User.med_center_id, User.address)
        .join(MedCentre, User.med_center_id == MedCentre.id_center)
        .filter(User.role == "main-doctor")
        .all()
    )
    return [
        MainDoctorResponse(
            id=id,
            full_name=full_name,
            email=email,
            password=password,
            center_name=center_name,
            med_center_id=med_center_id,
            address=address
        )
        for id, full_name, email, password, center_name, med_center_id, address in doctors
    ]

@app.get("/admins", response_model=List[MainDoctorResponse])
def get_admins(db: Session = Depends(get_db)):
    doctors = (
        db.query(User.id, User.full_name, User.email, User.password, MedCentre.center_name, User.med_center_id, User.address)
        .join(MedCentre, User.med_center_id == MedCentre.id_center)
        .filter(User.role == "admin")
        .all()
    )
    return [
        MainDoctorResponse(
            id=id,
            full_name=full_name,
            email=email,
            password=password,
            center_name=center_name,
            med_center_id=med_center_id,
            address=address
        )
        for id, full_name, email, password, center_name, med_center_id, address in doctors
    ]

@app.delete("/delete-doctor/{doctor_id}")
def delete_doctor(doctor_id: int, db: Session = Depends(get_db)):
    doctor = db.query(User).filter(User.id == doctor_id, User.role == "main-doctor").first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Главный врач не найден")

    db.delete(doctor)
    db.commit()
    return {"message": "Врач успешно удалён"}

@app.delete("/delete-admin/{doctor_id}")
def delete_doctor(doctor_id: int, db: Session = Depends(get_db)):
    doctor = db.query(User).filter(User.id == doctor_id, User.role == "admin").first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Администратор не найден")

    db.delete(doctor)
    db.commit()
    return {"message": "Администратор успешно удалён"}

@app.post("/add-doctor")
def add_doctor(request: MainDoctorResponse, db: Session = Depends(get_db)):
    new_doctor = User(
        email=request.email,
        password=request.password,
        full_name=request.full_name,
        med_center_id=request.med_center_id,
        role="main-doctor",
        address=request.address
    )
    db.add(new_doctor)
    db.commit()
    db.refresh(new_doctor)
    return {"message": "Врач успешно добавлен", "doctor_id": new_doctor.id}

@app.post("/add-admin")
def add_admin(request: MainDoctorResponse, db: Session = Depends(get_db)):
    new_doctor = User(
        email=request.email,
        password=request.password,
        full_name=request.full_name,
        med_center_id=request.med_center_id,
        role="admin",
        address=request.address
    )
    db.add(new_doctor)
    db.commit()
    db.refresh(new_doctor)
    return {"message": "Врач успешно добавлен", "doctor_id": new_doctor.id}

@app.put("/update-doctor/{doctor_id}")
def update_doctor(doctor_id: int, request: MainDoctorResponse, db: Session = Depends(get_db)):
    doctor = db.query(User).filter(User.id == doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Врач не найден")

    doctor.full_name = request.full_name
    doctor.email = request.email
    doctor.password = request.password
    doctor.med_center_id = request.med_center_id
    doctor.address = request.address

    try:
        db.commit()
        db.refresh(doctor)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Ошибка при обновлении данных врача")

    return {"message": "Данные врача успешно обновлены", "doctor": doctor}

@app.put("/update-admin/{doctor_id}")
def update_admin(doctor_id: int, request: MainDoctorResponse, db: Session = Depends(get_db)):
    doctor = db.query(User).filter(User.id == doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Врач не найден")

    doctor.full_name = request.full_name
    doctor.email = request.email
    doctor.password = request.password
    doctor.med_center_id = request.med_center_id
    doctor.address = request.address

    try:
        db.commit()
        db.refresh(doctor)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Ошибка при обновлении данных врача")

    return {"message": "Данные администратора успешно обновлены", "doctor": doctor}

@app.get("/polyclinics", response_model=List[PolyclinicResponse])
def get_polyclinics(db: Session = Depends(get_db)):
    centers = db.query(MedCentre.id_center, MedCentre.center_name).all()
    return [PolyclinicResponse(id_center=id_center, center_name=center_name) for id_center, center_name in centers]

@app.get("/med-centers", response_model=List[MedCenResponse])
def get_med_centres(db: Session = Depends(get_db)):
    centers = db.query(MedCentre.id_center, MedCentre.center_name, MedCentre.center_description, MedCentre.center_address, MedCentre.center_number).all()
    return [MedCenResponse(id_center=id_center, center_name=center_name, center_description = center_description, center_address = center_address, center_number = center_number) for id_center, center_name, center_description,center_address,center_number in centers]

@app.post("/add-med-center")
def add_med_center(request: MedCenResponse, db: Session = Depends(get_db)):
    new_med = MedCentre(
        center_name=request.center_name,
        center_description=request.center_description,
        center_address=request.center_address,
        center_number=request.center_number
    )
    db.add(new_med)
    db.commit()
    db.refresh(new_med)
    return {"message": "Мед центр успешно добавлен"}

@app.put("/update-med-center/{id_center}")
def update_med_center(id_center: int, request: MedCenResponse, db: Session = Depends(get_db)):
    med_center = db.query(MedCentre).filter(MedCentre.id_center == id_center).first()
    if not med_center:
        raise HTTPException(status_code=404, detail="Мед центр не найден")

    med_center.center_name = request.center_name
    med_center.center_description = request.center_description
    med_center.center_address = request.center_address
    med_center.center_number = request.center_number

    try:
        db.commit()
        db.refresh(med_center)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Ошибка при обновлении данных мед центра")

    return {"message": "Данные мед центра успешно обновлены", "center": med_center}


@app.delete("/delete-med-center/{id_center}")
def delete_med_center(id_center: int, db: Session = Depends(get_db)):
    med_center = db.query(MedCentre).filter(MedCentre.id_center == id_center).first()
    if not med_center:
        raise HTTPException(status_code=404, detail="Мед центр не найден")

    db.delete(med_center)
    db.commit()
    return {"message": "Мед центр успешно удалён"}
