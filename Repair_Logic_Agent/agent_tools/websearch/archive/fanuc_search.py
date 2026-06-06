import requests
from bs4 import BeautifulSoup
import urllib.parse
import time

def search(query):
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64 AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36)'}
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    results = []
    for a in soup.find_all('a', class_='result__url'):
        snippet = a.find_next(class_='result__snippet')
        title = a.find_previous(class_='result__title')
        href = a.get('href')
        if href and href.startswith('//duckduckgo.com/l/?uddg='):
            href = urllib.parse.unquote(href.split('uddg=')[1].split('&')[0])
        results.append({
            'url': href,
            'title': title.text.strip() if title else '',
            'snippet': snippet.text.strip() if snippet else ''
        })
    return results

queries = [
    "Fanuc 0i alarm error site:practicalmachinist.com",
    "Fanuc 31i error troubleshooting site:cnczone.com",
    "Fanuc spindle alarm site:practicalmachinist.com",
    "Fanuc servo alarm fix site:cnczone.com"
]

for q in queries:
    print(f"=== {q} ===")
    for r in search(q)[:4]:
        print(f"Title: {r['title']}\nURL: {r['url']}\nSnippet: {r['snippet']}\n")
    time.sleep(1.5)
