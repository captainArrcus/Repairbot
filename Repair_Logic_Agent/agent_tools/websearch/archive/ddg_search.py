import requests
from bs4 import BeautifulSoup
import urllib.parse
import time

def search(query):
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    results = []
    for a in soup.find_all('a', class_='result__url'):
        snippet = a.find_next(class_='result__snippet')
        title = a.find_previous(class_='result__title')
        results.append({
            'url': a.get('href'),
            'title': title.text.strip() if title else '',
            'snippet': snippet.text.strip() if snippet else ''
        })
    return results

print("=== PracticalMachinist ===")
for r in search("Heidenhain iTNC 530 error site:practicalmachinist.com")[:2]:
    print(r['title'], "-", r['snippet'])
time.sleep(1)

print("\n=== CNC Zone ===")
for r in search("Heidenhain TNC error site:cnczone.com")[:3]:
    print(r['title'], "-", r['snippet'])
time.sleep(1)

