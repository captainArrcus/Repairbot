from duckduckgo_search import DDGS
import time

def search_ddg(query):
    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=5):
            results.append(r)
            
    print(f"=== {query} ===")
    for r in results:
        print(f"TITLE: {r['title']}\nSUMMARY: {r['body']}\nURL: {r['href']}\n")
    time.sleep(1)

try:
    search_ddg("Fanuc 0i alarm fix site:practicalmachinist.com")
    search_ddg("Fanuc 18i alarm site:industryarena.com")
    search_ddg("Fanuc 31i error fix site:practicalmachinist.com")
except Exception as e:
    print(e)
