#!/bin/python
import os
import requests
import argparse

from dotenv import load_dotenv

load_dotenv()

def send_alarm(tgid: int, message: str) -> requests.Response:
    """
    function for sending notifications to telegram
    :param tgid: your telegram id
    :param message: message text
    """
    bot_token = os.getenv("TG_BOT_TOKEN")
    send_message_url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
	    
    payload = {
	    'chat_id': tgid,
	    'text': message
    }
	    
    resp = requests.post(send_message_url, data=payload)
    return resp

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("chat_id")
    parser.add_argument("message")

    args = parser.parse_args()
    send_alarm(args.chat_id, args.message)


if __name__ == "__main__":
    main()


