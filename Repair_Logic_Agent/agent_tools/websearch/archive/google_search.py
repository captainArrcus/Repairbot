import requests
from bs4 import BeautifulSoup
import urllib.parse
import time

def search(query):
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/110.0.0.0 Safari/537.36'}
    response = requests.get(url, headers=headers)
    if 'div class="result"' not in response.text and 'result__title' not in response.text:
       # fallback to google 
       url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
       response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/111.0'})
       soup = BeautifulSoup(response.text, 'html.parser')
       results = []
       for g in soup.find_all('div', class_='g'):
           title = g.find('h3')
           snippet = g.find('div', style=lambda value: value and '-webkit-line-clamp' in value)
           if not snippet:
               snippet = g.find('div', class_='VwiC3b')
           if title:
               href = g.find('a')['href'] if g.find('a') else ''
               results.append({
                   'url': href,
                   'title': title.text.strip(),
                   'snippet': snippet.text.strip() if snippet else ''
               })
       return results
    
    soup = BeautifulSoup(response.text, 'html.parser')
    results = []
    for a in soup.find_all('a', class_='result__url'):
        snippet = a.find_next(class_='result__snippet')
        title = a.find_previous(class_='result__title')
        href = a.get('href')
        results.append({
            'url': href,
            'title': title.text.strip() if title else '',
            'snippet': snippet.text.strip() if snippet else ''
        })
    return results

queries = [
    "Fanuc 0i error troubleshooting site:practicalmachinist.com",
    "Fanuc 31i servo alarm site:cnczone.com",
    "Fanuc spindle alarm problem fix site:practicalmachinist.com",
    "Fanuc 18i alarm repair fix site:industryarena.com"
]

for q in queries:
    print(f"=== {q} ===")
    for r in search(q)[:4]:
        print(f"Title: {r['title']}\nSnippet: {r['snippet']}\n")
    time.sleep(2)
