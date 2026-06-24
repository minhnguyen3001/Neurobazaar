# client_get_token.py
import requests

url = "http://127.0.0.1:8000/api/token/"
data = {
    "username": "admin",
    "password": "thisisatest",
}

response = requests.post(url, json=data)
print(response.json())


