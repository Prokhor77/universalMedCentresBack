import asyncio
from aiogram import Bot, Dispatcher, types, F
import requests

API_TOKEN = "8059699921:AAE8CGHPAK2sT6kyb07K-CT2UWS_OdeG2AM"
BASE_URL = "http://127.0.0.1:8080"
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Команда /start
@dp.message(F.text == "/start")
async def start(msg: types.Message):
    await msg.answer("Введите 4-значный код для привязки аккаунта:")

def send_record_telegram(tg_id, patient_name, doctor_name, doctor_specialization, date, time, description, assignment, paid_or_free, price, photo_urls):
    text = (
        f"<b>Ваш прием завершен!</b>\n"
        f"<b>Пациент:</b> {patient_name}\n"
        f"<b>Врач:</b> {doctor_name}\n"
        f"<b>Специализация:</b> {doctor_specialization}\n"
        f"<b>Дата:</b> {date}\n"
        f"<b>Время:</b> {time}\n"
        f"<b>Описание:</b> {description}\n"
        f"<b>Назначения:</b> {assignment}\n"
        f"<b>Тип приема:</b> {paid_or_free}\n"
        f"<b>Цена:</b> {price if price else '—'}\n"
    )
    send_telegram_message(tg_id, text)
    # Отправка фото отдельными сообщениями
    for url in photo_urls:
        try:
            requests.post(
                f"https://api.telegram.org/bot{API_TOKEN}/sendPhoto",
                data={"chat_id": tg_id, "photo": f"{BASE_URL}{url}"}
            )
        except Exception as e:
            print(f"Ошибка отправки фото в Telegram: {e}")

def send_telegram_message(tg_id, text):
    url = f"https://api.telegram.org/bot{API_TOKEN}/sendMessage"
    data = {
        "chat_id": tg_id,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, data=data)
    except Exception as e:
        print(f"Ошибка отправки в Telegram: {e}")

# 4-значный код
@dp.message(F.text.regexp(r"^\d{4}$"))
async def bind_code(msg: types.Message):
    code = msg.text
    tg_id = msg.from_user.id
    try:
        resp = requests.post(f"{BASE_URL}/tg-bind/confirm", json={"code": code, "tg_id": tg_id})
        if resp.status_code == 200:
            fio = resp.json().get("message", "Аккаунт успешно привязан")
            await msg.answer(fio)
        else:
            await msg.answer("Код не найден или уже использован.")
    except Exception as e:
        await msg.answer(f"Ошибка: {e}")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())