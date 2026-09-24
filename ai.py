"""Standalone one-off prompt script (not part of the bot).

The key now comes from .env via config.py instead of being pasted in here.
"""
import requests

import config

url = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{config.GEMINI_MODEL}:generateContent"
)

headers = {
    "x-goog-api-key": config.GEMINI_API_KEY,
    "Content-Type": "application/json",
}
prompt = input("Ask the AI: ")

data = {
    "contents": [
        {
            "parts": [
                {"text": prompt}
            ]
        }
    ]
}

response = requests.post(url, headers=headers, json=data)
result = response.json()

if response.status_code != 200:
    print("Error:", result.get("error", {}).get("message", response.status_code))
else:
    print(result["candidates"][0]["content"]["parts"][0]["text"])
