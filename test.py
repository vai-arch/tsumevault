import requests

url = "https://goproblems.com/api/collections?text=&offset=0&limit=10&order=Size&sortDirection=desc"
print(requests.get(url, headers={"User-Agent": "Mozilla/5.0"}).json())
