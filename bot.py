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