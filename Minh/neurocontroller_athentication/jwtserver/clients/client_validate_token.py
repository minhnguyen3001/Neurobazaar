import requests

ACCESS_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzY5MDM4ODM4LCJpYXQiOjE3NjkwMzYxMzgsImp0aSI6ImNhMzMxYjgxZThjODRhNDlhZWEyZDI3NGQwNWZhODkzIiwidXNlcl9pZCI6IjIifQ.kdBExsGWVQXwmdkIBrcKenYzJwosWZ4fVMwY_1XX2mM"


headers = {
    "Authorization": f"Bearer {ACCESS_TOKEN}"
}

url = "http://127.0.0.1:8000/api/protected/"
response = requests.get(url, headers=headers)

print(response.status_code)
print(response.json())





