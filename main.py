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

class WorkType(Base):
    __tablename__ = "work_types"
    type_id = Column(Integer, primary_key=True, index=True)
    type_description = Column(String, nullable=False)

class WorkSection(Base):
    __tablename__ = "work_sections"
    section_id = Column(Integer, primary_key=True, index=True)
    section_description = Column(String, nullable=False)

class Doctor(Base):
    __tablename__ = "doctors"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    work_type_id = Column(Integer, ForeignKey("work_types.type_id"))
    work_section_id = Column(String, ForeignKey("work_sections.section_id"))
    work_experience = Column(String)

# Создание таблиц
Base.metadata.create_all(bind=engine)

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

class PolyclinicResponse(BaseModel):
    id_center: int
    center_name: str

class MedCenResponse(BaseModel):
    id_center: int
    center_name: str
    center_description: str
    center_address: str
    center_number: int

class DoctorResponse(BaseModel):
    id: int
    full_name: str
    email: str
    password: str
    center_name: str
    med_center_id: int
    address: str
    work_type_description: str
    work_section_description: str

    class Config:
        orm_mode = True

class WorkSectionResponse(BaseModel):
    section_id: int
    section_description: str

    class Config:
        orm_mode = True

class WorkTypeResponse(BaseModel):
    type_id: int
    type_description: str

    class Config:
        orm_mode = True

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

@app.get("/doctors", response_model=List[DoctorResponse])
def get_doctors(db: Session = Depends(get_db)):
    doctors = (
        db.query(
            User.id,
            User.full_name,
            User.email,
            User.password,
            MedCentre.center_name,
            User.med_center_id,
            User.address,
            WorkType.type_description.label("work_type_description"),
            Doctor.work_section_id  # Получаем список ID секций
        )
        .join(MedCentre, User.med_center_id == MedCentre.id_center)
        .join(Doctor, User.id == Doctor.user_id)
        .join(WorkType, Doctor.work_type_id == WorkType.type_id)
        .filter(User.role == "doctor")
        .all()
    )

    doctor_list = []
    for id, full_name, email, password, center_name, med_center_id, address, work_type_description, work_section_ids in doctors:
        section_descriptions = []
        if work_section_ids:
            section_ids = [int(sec_id) for sec_id in work_section_ids.split(",")]  # Разбиваем ID
            sections = db.query(WorkSection.section_description).filter(WorkSection.section_id.in_(section_ids)).all()
            section_descriptions = [sec[0] for sec in sections]  # Получаем текст описаний

        doctor_list.append(
            DoctorResponse(
                id=id,
                full_name=full_name,
                email=email,
                password=password,
                center_name=center_name,
                med_center_id=med_center_id,
                address=address,
                work_type_description=work_type_description,
                work_section_description=", ".join(section_descriptions)  # Объединяем в строку
            )
        )

    return doctor_list

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

@app.delete("/delete-main-doctor/{doctor_id}")
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

@app.post("/add-main-doctor")
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

@app.put("/update-main-doctor/{doctor_id}")
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

@app.get("/work-sections", response_model=List[WorkSectionResponse])
def get_work_sections(db: Session = Depends(get_db)):
    """
    Возвращает список всех разделов работы (work_sections).
    """
    work_sections = db.query(WorkSection.section_id, WorkSection.section_description).all()
    return [
        WorkSectionResponse(
            section_id=section_id,
            section_description=section_description
        )
        for section_id, section_description in work_sections
    ]

@app.get("/work-types", response_model=List[WorkTypeResponse])
def get_work_types(db: Session = Depends(get_db)):
    """
    Возвращает список всех типов работы (work_types).
    """
    work_types = db.query(WorkType.type_id, WorkType.type_description).all()
    return [
        WorkTypeResponse(
            type_id=type_id,
            type_description=type_description
        )
        for type_id, type_description in work_types
    ]

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
