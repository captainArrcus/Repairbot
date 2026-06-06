import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'Repair_Logic_Agent', 'agent_tools', 'websearch'))
from unified_search import UnifiedSearchEngine

# Expand query to get broader results for just Heidenhain TNC error
query = '(Heidenhain TNC error OR Heidenhain iTNC 530 error) (site:practicalmachinist.com OR site:cnczone.com OR site:industryarena.com)'
engine = UnifiedSearchEngine()
results = engine.unified_search(query, max_results=15)
for res in results:
    if hasattr(res, "__dict__"): 
        print(f"URL: {res.url}\nTitle: {res.title}\nSnippet: {res.snippet}\n")
    elif isinstance(res, dict):
        print(f"URL: {res.get('url', res.get('href'))}\nTitle: {res.get('title')}\nSnippet: {res.get('snippet', res.get('body'))}\n")
