import requests

ACCESS_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzY5MDM4ODM4LCJpYXQiOjE3NjkwMzYxMzgsImp0aSI6ImNhMzMxYjgxZThjODRhNDlhZWEyZDI3NGQwNWZhODkzIiwidXNlcl9pZCI6IjIifQ.kdBExsGWVQXwmdkIBrcKenYzJwosWZ4fVMwY_1XX2mM"
REFRESH_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc2OTEyMjUzOCwiaWF0IjoxNzY5MDM2MTM4LCJqdGkiOiJkMTEyYzIxNjkzNWE0ZjVjODlhYzNiMDM5ZmZhYTMwYiIsInVzZXJfaWQiOiIyIn0.9REgcfRHZWbv_LC8xrSbYQIqJf_VWnkGmE9Ri-k4viM"

REVOKE_URL = "http://127.0.0.1:8000/api/protected/"


def revoke_token(access_token: str, refresh_token: str):
    """
    Revoke refresh token.
    Rejects unauthorized requests and handles invalid/unavailable tokens.
    """

    if not access_token or not refresh_token:
        raise ValueError("Access token or refresh token is missing")

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    payload = {
        "refresh": refresh_token
    }

    try:
        response = requests.post(
            REVOKE_URL,
            json=payload,
            headers=headers,
            timeout=5
        )
    except requests.exceptions.RequestException as e:
        print("Network or connection error:", e)
        return

    # ---- Handle response codes ----
    if response.status_code == 200:
        print("Token revoked successfully.")
        return

    if response.status_code == 401:
        print("Unauthorized request: access token is invalid or expired.")
        return

    if response.status_code == 403:
        print("Forbidden: you do not have permission to revoke this token.")
        return

    if response.status_code == 400:
        print("Bad request: refresh token is invalid or already revoked.")
        return

    # ---- Catch-all for other errors ----
    print("Unexpected error:", response.status_code)
    try:
        print("Response:", response.json())
    except ValueError:
        print("Response text:", response.text)


if __name__ == "__main__":
    revoke_token(ACCESS_TOKEN, REFRESH_TOKEN)
