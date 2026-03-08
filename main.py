import requests

url = "https://api.cludo.com/api/v3/search"

params = {
    "query": "tax on hackathon winning",
    "page": 1,
    "per_page": 10
}

headers = {
    "Content-Type": "application/json"
}

r = requests.get(url, params=params, headers=headers)

data = r.json()

print(data)