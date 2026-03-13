import requests
from bs4 import BeautifulSoup

url = "https://www.caclubindia.com/search_results_new.asp?q=tax+on+hackathon+winning#gsc.tab=0&gsc.q=tax%20on%20hackathon%20winning&gsc.page=1"

headers = {
    "User-Agent": "Mozilla/5.0"
}

html = requests.get(url, headers=headers).text

soup = BeautifulSoup(html, "html.parser")

results = soup.select(".gsc-webResult")

for r in results:
    title = r.select_one("a.gs-title")
    snippet = r.select_one(".gs-snippet")

    if title:
        link = title["href"]
        text = title.get_text(strip=True)

        desc = snippet.get_text(strip=True) if snippet else ""

        print(text)
        print(link)
        print(desc)
        print()