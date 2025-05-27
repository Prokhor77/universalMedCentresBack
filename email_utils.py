import os
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_record_email(to_email, patient_name, doctor_name, doctor_specialization, date, time, description, assignment, paid_or_free, price, photo_urls):
    username = "prohor.odinets@yandex.by"
    password = "hgrgaosbzvtxdxam"
    smtp_server = "smtp.yandex.com"
    smtp_port = 587

    msg = MIMEMultipart()
    msg['From'] = username
    msg['To'] = to_email
    msg['Subject'] = "Информация о приеме"

    html = f"""
    <html>
    <body>
        <h2>Ваш прием завершен!</h2>
        <p><b>Пациент:</b> {patient_name}</p>
        <p><b>Врач:</b> {doctor_name}</p>
        <p><b>Специализация:</b> {doctor_specialization}</p>
        <p><b>Дата:</b> {date}</p>
        <p><b>Время:</b> {time}</p>
        <p><b>Описание:</b> {description}</p>
        <p><b>Назначения:</b> {assignment}</p>
        <p><b>Тип приема:</b> {paid_or_free}</p>
        <p><b>Цена:</b> {price if price else '—'}</p>
        <p><b>Фото:</b> во вложениях</p>
    </body>
    </html>
    """
    msg.attach(MIMEText(html, 'html'))

    # Добавляем фото как вложения
    for url in photo_urls:
        # url должен быть локальным путем к файлу, например: "/uploads/abc.jpg"
        file_path = url
        if file_path.startswith("/"):
            file_path = file_path[1:]
        if not os.path.exists(file_path):
            continue
        with open(file_path, "rb") as f:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename="{os.path.basename(file_path)}"')
            msg.attach(part)

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(username, password)
        server.sendmail(username, to_email, msg.as_string())
        server.quit()
    except Exception as e:
        print(f"Ошибка отправки email: {e}")

def send_appointment_email(to_email, doctor_name, doctor_specialization, date, time):
    username = "prohor.odinets@yandex.by"
    password = "hgrgaosbzvtxdxam"
    smtp_server = "smtp.yandex.com"
    smtp_port = 587

    msg = MIMEMultipart()
    msg['From'] = username
    msg['To'] = to_email
    msg['Subject'] = "Запись к врачу"

    html = f"""
    <html>
    <body>
        <h2>Вы записались к врачу!</h2>
        <p><b>Врач:</b> {doctor_name}</p>
        <p><b>Специализация:</b> {doctor_specialization}</p>
        <p><b>Дата:</b> {date}</p>
        <p><b>Время:</b> {time}</p>
    </body>
    </html>
    """
    msg.attach(MIMEText(html, 'html'))

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(username, password)
        server.sendmail(username, to_email, msg.as_string())
        server.quit()
    except Exception as e:
        print(f"Ошибка отправки email: {e}")