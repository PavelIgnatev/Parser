from telethon.sessions import StringSession
from telethon import TelegramClient
from telethon.tl.types import Channel
from telethon import functions, errors
from datetime import datetime
import server_save
import datetime
import string
import random
import logging
import asyncio
import time
import json
import schedule
import os
import requests
import sys

my_variable = os.environ.get("ID")
print(my_variable)
with open("query_keys.json", "r") as f:
    queryKey = json.load(f) or []

task_running = False

logging.basicConfig(
    level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)
file_handler = logging.FileHandler("chat_parser.log")
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(
    logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
)
logger.addHandler(file_handler)


def generate_random_string(length):
    letters = string.ascii_letters
    return "".join(random.choice(letters) for _ in range(length))


def get_username(entity):
    if hasattr(entity, "username") and entity.username is not None:
        return entity.username
    else:
        return None


def serialize_participant(participant):
    if hasattr(participant, "status"):
        if hasattr(participant.status, "was_online"):
            last_online = participant.status.was_online.strftime("%Y-%m-%d %H:%M:%S")
        else:
            last_online = None
    else:
        last_online = None
    if hasattr(participant, "photo"):
        if participant.photo is not None:
            image = True
        else:
            image = False
    else:
        image = False
    return {
        "username": (participant.username if hasattr(participant, "username") else None),
        "first_name": (participant.first_name if hasattr(participant, "first_name") else None),
        "last_name": (
            participant.last_name if hasattr(participant, "last_name") else None
        ),
        "last_online": last_online,
        "premium": (
            participant.premium
            if (hasattr(participant, "premium") and participant.premium is not None)
            else False
        ),
        "phone": (participant.phone if hasattr(participant, "phone") else None),
        "image": image
    }


async def send_request_to_server(user_data, retry_delay=5):
    if not any(user_data.values()):
        logger.error("Попытка сохранить пустые данные. Отмена сохранения.")
        return
    while True:
        try:
            logger.info(f"Инициирую запрос на сохранение данных локально.")
            await server_save.background_save(user_data)
            return
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка при сохранении данных на сервер: {e}")
            time.sleep(retry_delay)


async def parse_chat(client, chat, user_data):
    try:
        logger.info(f"Обработка чата: {chat.title}")
        chat_data = {
            "username": chat.username,
            "title": chat.title if hasattr(chat, "title") else None,
            "last_online": (
                chat.date.strftime("%Y-%m-%d %H:%M:%S")
                if chat.date and hasattr(chat, "date")
                else None
            ),
        }
        user_data["chats"][chat.id] = chat_data

        try:
            total_messages = (await client.get_messages(chat, 1)).total
        except Exception as e:
            logger.error(
                f"Произошла ошибка при получении сообщений в чате: {chat.title}, {e}"
            )
            return

        processed_participants = 0
        total_participants = 0

        for letter in queryKey:
            try:
                logger.info(
                    f"Начинаю получать участников по букве {letter} в чате {chat.title}"
                )
                participants = await client.get_participants(chat, search=letter)
                total_participants += len(participants)

                for participant in participants:
                    processed_participants += 1
                    logger.info(
                        f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Обработка участника {processed_participants}/{total_participants}"
                    )

                    if not isinstance(participant, Channel) and not getattr(
                            participant, "bot", False
                    ):

                        if True:
                            if participant.id not in user_data["accounts"]:
                                user_data["accounts"][participant.id] = {
                                    "chats": {chat.id: []},
                                }
                            else:
                                if (
                                        chat.id
                                        not in user_data["accounts"][participant.id]["chats"]
                                ):
                                    user_data["accounts"][participant.id]["chats"][
                                        chat.id
                                    ] = []

                            info = serialize_participant(participant)
                            user_data["accounts"][participant.id][
                                "info"
                            ] = info
            except Exception as e:
                logger.error(
                    f"Произошла ошибка при получении участников по букве {letter} в чате {chat.title}: {e}"
                )
        processed_messages = 0

        async for message in client.iter_messages(chat, limit=100):    # сократила, чтобы он быстрее обрабатывал
            sender = message.sender
            if (
                    sender is not None
                    and not isinstance(sender, Channel)
                    and not getattr(sender, "bot", False)

            ):

                if True:
                    if sender.id not in user_data["accounts"]:
                        user_data["accounts"][sender.id] = {
                            "chats": {chat.id: []},
                        }
                    else:
                        if (
                                chat.id
                                not in user_data["accounts"][sender.id]["chats"]
                        ):
                            user_data["accounts"][sender.id]["chats"][
                                chat.id
                            ] = []

                    info = serialize_participant(sender)
                    user_data["accounts"][sender.id]["info"] = info

                    processed_messages += 1
                    progress = processed_messages / total_messages * 100
                    logger.info(
                        f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Обработка сообщений: {processed_messages}/{total_messages} ({progress:.2f}%)"
                    )

                    if message.text and message.text.strip() != "":
                        user_data["accounts"][sender.id]["chats"][
                            chat.id
                        ].append({"message_id": message.id, "text": message.text})

    except Exception as e:
        logger.error(f"Произошла ошибка при обработке чата. {e}")
        logger.exception(e)


async def parse_chat_by_username(client, chat_url_or_username, user_data):
    chat = await client.get_entity(chat_url_or_username)

    if chat.megagroup:
        logger.info(f"Чат {chat_url_or_username} в работе.")
        await parse_chat(client, chat, user_data)
    else:
        logger.info(
            f"Ссылка {chat_url_or_username} не является чатом, попытка извлечь чат..."
        )
        full = await client(functions.channels.GetFullChannelRequest(chat))
        if full and full.chats:
            for chat in full.chats:
                if chat is not None and chat.megagroup:
                    logger.info(
                        f"Исходя из ссылки {chat_url_or_username} найден прикрепленный чат {chat.id}."
                    )
                    logger.info(
                        f"Чат {chat.id} от канала {chat_url_or_username} в работе."
                    )
                    await parse_chat(client, chat, user_data)


async def main(chat_urls_or_usernames, api_id, api_hash, session_value):
    global task_running
    task_running = True
    user_data = {"chats": {}, "accounts": {}}
    try:
        async with TelegramClient(
                StringSession(session_value), api_id, api_hash
        ) as client:
            for chat_url_or_username in chat_urls_or_usernames:
                try:
                    await parse_chat_by_username(
                        client, chat_url_or_username, user_data
                    )
                    await send_request_to_server(user_data)
                except errors.FloodWaitError as e:
                    try:
                        wait_time = e.seconds
                        logger.warning(
                            f"Получена ошибка FloodWaitError. Ожидание {wait_time} секунд перед повторной попыткой..."
                        )
                        await asyncio.sleep(wait_time + 5)
                        await parse_chat_by_username(
                            client, chat_url_or_username, user_data
                        )
                        await send_request_to_server(user_data)
                    except Exception as e:
                        logger.error(f"Произошла ошибка при повторном парсен: {e}")
                except Exception as e:
                    logger.error(
                        f"Ссылка {chat_url_or_username} не распаршена, произошла ошибка. {e}"
                    )
                    continue

    except Exception as e:
        logger.error(f"Произошла глобальная ошибка. {e}")
    task_running = False

async def background_task(
        chat_urls_or_usernames, api_id, api_hash, session_value
):
    await main(chat_urls_or_usernames, api_id, api_hash, session_value)

async def handle_task(api_id, api_hash, session_value):
        print(f"ID: {api_id}")
        print(f"HASH: {api_hash}")
        print(f"SESSION_VALUE: {session_value}")
        try:
            async with TelegramClient(StringSession(session_value), api_id, api_hash) as client:
                me = await client.get_me()
                res = requests.get("http://localhost/link") #
                data = res.json()
                chat_urls_or_usernames = []
                chat_urls_or_usernames.append(data)
                logger.info(f"{chat_urls_or_usernames}")
                logger.info(f"Телеграм аккаунт работает, идентификатор пользователя: {me.id}")

                await background_task(
                            chat_urls_or_usernames, api_id, api_hash, session_value
                        )

        except Exception as e:
            logger.error(f"Произошла ошибка при проверке работы Telegram аккаунта: {e}")

schedule.every(1).minutes.do(handle_task)
api_id = sys.argv[1]
api_hash = sys.argv[2]
session_value = sys.argv[3]
async def do_POST():
    await handle_task(api_id, api_hash, session_value)

async def keep():
    while True:
        await do_POST()
        await asyncio.sleep(60)

if __name__ == "main":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())

asyncio.run(keep())


