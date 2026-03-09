import requests
import json

url = "https://api.klipy.com/api/v1/{app_key}/autocomplete/{q}?limit=10"

payload = {}
headers = {
  'Content-Type': 'application/json'
}

response = requests.request("GET", url, headers=headers, data=payload)

print(response.text)
