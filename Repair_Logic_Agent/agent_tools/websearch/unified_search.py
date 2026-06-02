"""
Unified Search Engine Module

This module combines multiple search engines and file processing capabilities:
- Google Custom Search API (with advanced filtering)
- DuckDuckGo Search
- Google Search (fallback with scraping)
- Tavily Search
- File processing for various formats (PDF, Excel, websites)

Features:
- Exact string matching with quotes
- Advanced filtering (date, country, language, etc.)
- Multiple search engines for redundancy
- Automatic file type detection and processing
- Rate limiting and error handling
- Result comparison and deduplication
"""

import os
import time
import random

# Core dependencies
try:
    import requests
except ImportError:
    print("Warning: requests not available. Some functionality will be limited.")
    requests = None

# Optional dependencies with graceful fallbacks
try:
    from googlesearch import search
    GOOGLESEARCH_AVAILABLE = True
except ImportError:
    print("Warning: googlesearch-python not available. Google scraping disabled.")
    GOOGLESEARCH_AVAILABLE = False

try:
    from ddgs import DDGS
    DUCKDUCKGO_AVAILABLE = True
except ImportError:
    try:
        from duckduckgo_search import DDGS
        DUCKDUCKGO_AVAILABLE = True
    except ImportError:
        print("Warning: ddgs (formerly duckduckgo-search) not available. DuckDuckGo search disabled.")
        DUCKDUCKGO_AVAILABLE = False

try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_API_AVAILABLE = True
except ImportError:
    print("Warning: google-api-python-client not available. Google API search disabled.")
    GOOGLE_API_AVAILABLE = False

try:
    from tavily import TavilyClient
    TAVILY_AVAILABLE = True
except ImportError:
    print("Warning: tavily-python not available. Tavily search disabled.")
    TAVILY_AVAILABLE = False

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("Warning: python-dotenv not available. Using environment variables directly.")
    pass

# User agents for web scraping
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
]


class UnifiedSearchEngine:
    """
    A unified search engine that combines multiple search providers
    """
    
    def __init__(self):
        self.google_api_key = os.getenv("GOOGLE_SEARCH_API_KEY")
        self.google_cse_id = os.getenv("GOOGLE_CSE_ID")
        self.tavily_api_key = os.getenv("TAVILY_API_KEY")
        
        # Initialize Tavily client if available
        if TAVILY_AVAILABLE and self.tavily_api_key:
            self.tavily_client = TavilyClient(api_key=self.tavily_api_key)
        else:
            self.tavily_client = None
        
    def search_google_api(self, query, max_results=100, date_restrict=None, country=None, 
                         language=None, safe_search='off', sort_by_date=False, exact_match=True):
        """
        Search Google using the Custom Search JSON API with advanced filtering.
        
        Args:
            query (str): The search query
            max_results (int): Maximum results to fetch (up to 100)
            date_restrict (str): Time filter - 'd1', 'w1', 'm1', 'm3', 'm6', 'y1'
            country (str): Country code - 'us', 'uk', 'de', etc.
            language (str): Language - 'lang_en', 'lang_de', etc.
            safe_search (str): 'off', 'medium', 'high'
            sort_by_date (bool): Sort by date instead of relevance
            exact_match (bool): Whether to wrap query in quotes for exact matching
        
        Returns:
            list: A list of search result URLs
        """
        
        if not GOOGLE_API_AVAILABLE:
            print("Google API search not available - missing google-api-python-client")
            return []
        
        # Format query for exact matching if requested
        search_term = f'"{query}"' if exact_match else query
        
        if not self.google_cse_id or not self.google_api_key:
            print("Missing Google API credentials")
            return []
        
        try:
            service = build("customsearch", "v1", developerKey=self.google_api_key)
            all_results = []
            
            # Calculate pagination (max 100 results, 10 per request)
            max_results = min(max_results, 100)
            requests_needed = min((max_results + 9) // 10, 10)
            
            print(f"Google API: Searching for: {search_term}")
            if date_restrict:
                print(f"Date filter: {date_restrict}")
            
            for i in range(requests_needed):
                start_index = i * 10 + 1
                
                # Build request parameters
                params = {
                    'q': search_term,
                    'cx': self.google_cse_id,
                    'start': start_index,
                    'num': min(10, max_results - len(all_results))
                }
                
                # Add optional filters
                if date_restrict:
                    params['dateRestrict'] = date_restrict
                if country:
                    params['gl'] = country
                    params['cr'] = f'country{country.upper()}'
                if language:
                    params['lr'] = language
                if safe_search:
                    params['safe'] = safe_search
                if sort_by_date:
                    params['sort'] = 'date'
                
                print(f"Fetching results {start_index}-{start_index + params['num'] - 1}")
                
                res = service.cse().list(**params).execute()
                items = res.get("items", [])
                
                if not items:
                    print(f"No more results found (stopped at page {i + 1})")
                    break
                
                all_results.extend(items)
                print(f"Got {len(items)} results from this page")
                
                # Rate limiting between requests
                if i < requests_needed - 1:
                    time.sleep(0.1)
            
            urls = [item["link"] for item in all_results]
            print(f"Google API: Total results found: {len(urls)}")
            return urls
            
        except HttpError as e:
            print(f"Google API error: {e}")
            if "quotaExceeded" in str(e):
                print("Daily API quota exceeded")
            elif "Invalid Value" in str(e):
                print("Check your CSE_ID and API key")
            return []

    def search_google_scraping(self, search_term, num_results=10, sleep_range=(2, 5), max_retries=3, exact_match=True):
        """
        Search Google using web scraping as a fallback method.
        
        Args:
            search_term (str): The search query
            num_results (int): Number of results to fetch
            sleep_range (tuple): Min and max sleep time between requests
            max_retries (int): Maximum number of retry attempts
            exact_match (bool): Whether to wrap query in quotes for exact matching
            
        Returns:
            list: A list of search result URLs
        """
        
        if not GOOGLESEARCH_AVAILABLE:
            print("Google scraping not available - missing googlesearch-python")
            return []
            
        if not requests:
            print("Google scraping not available - missing requests")
            return []
        
        # Format query for exact matching if requested
        query = f'"{search_term}"' if exact_match else search_term
        results = []
        retries = 0

        while retries < max_retries:
            try:
                user_agent = random.choice(USER_AGENTS)

                # Monkey patch session for googlesearch library
                def get_page(url):
                    session = requests.Session()
                    session.headers["User-Agent"] = user_agent
                    req = requests.Request("GET", url, headers=session.headers)
                    prepared = session.prepare_request(req)
                    try:
                        response = session.send(prepared, stream=False, timeout=10)
                    except requests.exceptions.RequestException:
                        return None
                    return response.content.decode('UTF-8')
                
                # Apply monkey patch
                search.get_page = get_page

                print(f"Google Scraping: Searching for: {query}")
                search_results = search(query, num_results=num_results)

                for result in search_results:
                    results.append(result)

                print(f"Google Scraping: Found {len(results)} results")
                return results

            except Exception as e:
                print(f"Google scraping error (attempt {retries + 1}/{max_retries}): {e}")
                retries += 1
                if retries < max_retries:
                    wait_time = (2 ** retries) + random.random()
                    print(f"Waiting {wait_time:.2f} seconds before retrying...")
                    time.sleep(wait_time)
                else:
                    print("Max retries reached. Google scraping failed.")
                    return []

            finally:
                sleep_duration = random.uniform(sleep_range[0], sleep_range[1])
                time.sleep(sleep_duration)

        return []

    def search_duckduckgo(self, search_term, num_results=10, exact_match=True):
        """
        Search DuckDuckGo using their API.
        
        Args:
            search_term (str): The search query
            num_results (int): Number of results to fetch
            exact_match (bool): Whether to wrap query in quotes for exact matching
            
        Returns:
            list: A list of search result URLs
        """
        
        if not DUCKDUCKGO_AVAILABLE:
            print("DuckDuckGo search not available - missing duckduckgo-search")
            return []
        
        # Format query for exact matching if requested
        query = f'"{search_term}"' if exact_match else search_term
        
        try:
            print(f"DuckDuckGo: Searching for: {query}")
            results = DDGS().text(query, max_results=num_results)
            
            # Extract URLs from DuckDuckGo results
            urls = [result.get('href') for result in results if result.get('href')]
            print(f"DuckDuckGo: Found {len(urls)} results")
            return urls
            
        except Exception as e:
            print(f"DuckDuckGo search error: {e}")
            return []

    def search_duckduckgo_detailed(self, search_term, num_results=10, exact_match=True):
        """
        Search DuckDuckGo using their API and return detailed results.
        
        Args:
            search_term (str): The search query
            num_results (int): Number of results to fetch
            exact_match (bool): Whether to wrap query in quotes for exact matching
            
        Returns:
            list: A list of detailed search results with title, href, and body
        """
        
        if not DUCKDUCKGO_AVAILABLE:
            print("DuckDuckGo search not available - missing duckduckgo-search")
            return []
        
        # Format query for exact matching if requested
        query = f'"{search_term}"' if exact_match else search_term
        
        try:
            print(f"DuckDuckGo: Searching for: {query}")
            results = DDGS().text(query, max_results=num_results)
            
            # Return detailed results
            detailed_results = []
            for result in results:
                detailed_results.append({
                    'title': result.get('title', 'No title'),
                    'href': result.get('href', '#'),
                    'body': result.get('body', ''),
                })
            
            print(f"DuckDuckGo: Found {len(detailed_results)} results")
            return detailed_results
            
        except Exception as e:
            print(f"DuckDuckGo search error: {e}")
            return []

    def search_web_browser_results(self, query, max_results=10, filter_year=None):
        """
        Search for web browser results using the best available search engine.
        Returns detailed results suitable for web browser display.
        
        Args:
            query (str): The search query
            max_results (int): Maximum number of results to return
            filter_year (int): Optional year filter for results
            
        Returns:
            list: A list of detailed search results with title, href, and body
        """
        
        # Apply year filter to query if specified
        search_query = query
        if filter_year is not None:
            search_query = f"{query} site:*.{filter_year}.*"
        
        # Try DuckDuckGo first as it's most likely to be available
        if DUCKDUCKGO_AVAILABLE:
            results = self.search_duckduckgo_detailed(search_query, max_results)
            if results:
                return results
        
        # Fallback to Tavily if available
        if TAVILY_AVAILABLE and self.tavily_client:
            try:
                tavily_results = self.search_tavily_detailed(search_query, max_results)
                if tavily_results:
                    # Convert Tavily results to the expected format
                    results = []
                    for result in tavily_results:
                        results.append({
                            'title': result.get('title', 'No title'),
                            'href': result.get('url', '#'),
                            'body': result.get('content', ''),
                        })
                    return results
            except Exception as e:
                print(f"Tavily search failed: {e}")
        
        # Fallback to Google API if available
        if GOOGLE_API_AVAILABLE and self.google_api_key and self.google_cse_id:
            try:
                # Google API only returns URLs, so we'll need to use DuckDuckGo for details
                urls = self.search_google_api(search_query, max_results)
                if urls:
                    # Return simplified results with just URLs
                    results = []
                    for i, url in enumerate(urls):
                        results.append({
                            'title': f'Result {i+1}',
                            'href': url,
                            'body': 'Click to view content',
                        })
                    return results
            except Exception as e:
                print(f"Google API search failed: {e}")
        
        # No search engines available
        return []

    def search_tavily(self, query, max_results=10):
        """
        Search Tavily using their API.
        
        Args:
            query (str): The search query
            max_results (int): Maximum results to fetch
            
        Returns:
            list: A list of search result URLs
        """
        
        if not TAVILY_AVAILABLE:
            print("Tavily search not available - missing tavily-python")
            return []
        
        try:
            print(f"Tavily: Searching for: {query}")
            client = TavilyClient()
            results = client.search(query, limit=max_results)
            
            # Extract URLs from Tavily results
            urls = [result.get('url') for result in results if result.get('url')]
            print(f"Tavily: Found {len(urls)} results")
            return urls
            
        except Exception as e:
            print(f"Tavily search error: {e}")
            return []

    def search_tavily(self, search_term, num_results=10, search_depth="basic", include_domains=None, exclude_domains=None):
        """
        Search using Tavily API for comprehensive web search results.
        
        Args:
            search_term (str): The search query
            num_results (int): Number of results to fetch (max 20)
            search_depth (str): "basic" or "advanced" - depth of search
            include_domains (list): List of domains to include in search
            exclude_domains (list): List of domains to exclude from search
            
        Returns:
            list: A list of search result URLs
        """
        
        if not TAVILY_AVAILABLE:
            print("Tavily search not available - missing tavily-python")
            return []
            
        if not self.tavily_client:
            print("Tavily search not available - missing API key")
            return []
        
        try:
            print(f"Tavily: Searching for: {search_term}")
            
            # Prepare search parameters
            search_params = {
                "query": search_term,
                "search_depth": search_depth,
                "max_results": min(num_results, 20)  # Tavily has a max of 20 results
            }
            
            # Add domain filters if provided
            if include_domains:
                search_params["include_domains"] = include_domains
            if exclude_domains:
                search_params["exclude_domains"] = exclude_domains
            
            # Perform search
            response = self.tavily_client.search(**search_params)
            
            # Extract URLs from Tavily results
            urls = []
            if 'results' in response:
                for result in response['results']:
                    if 'url' in result:
                        urls.append(result['url'])
            
            print(f"Tavily: Found {len(urls)} results")
            return urls
            
        except Exception as e:
            print(f"Tavily search error: {e}")
            return []

    def search_tavily_detailed(self, search_term, num_results=10, search_depth="basic", include_domains=None, exclude_domains=None):
        """
        Search using Tavily API and return detailed results (not just URLs).
        
        Args:
            search_term (str): The search query
            num_results (int): Number of results to fetch (max 20)
            search_depth (str): "basic" or "advanced" - depth of search
            include_domains (list): List of domains to include in search
            exclude_domains (list): List of domains to exclude from search
            
        Returns:
            list: A list of detailed search result dictionaries
        """
        
        if not TAVILY_AVAILABLE:
            print("Tavily search not available - missing tavily-python")
            return []
            
        if not self.tavily_client:
            print("Tavily search not available - missing API key")
            return []
        
        try:
            print(f"Tavily (detailed): Searching for: {search_term}")
            
            # Prepare search parameters
            search_params = {
                "query": search_term,
                "search_depth": search_depth,
                "max_results": min(num_results, 20)
            }
            
            # Add domain filters if provided
            if include_domains:
                search_params["include_domains"] = include_domains
            if exclude_domains:
                search_params["exclude_domains"] = exclude_domains
            
            # Perform search
            response = self.tavily_client.search(**search_params)
            
            # Return full results with title, URL, content, etc.
            results = []
            if 'results' in response:
                for result in response['results']:
                    results.append({
                        'title': result.get('title', ''),
                        'url': result.get('url', ''),
                        'content': result.get('content', ''),
                        'score': result.get('score', 0)
                    })
            
            print(f"Tavily (detailed): Found {len(results)} results")
            return results
            
        except Exception as e:
            print(f"Tavily detailed search error: {e}")
            return []

    def unified_search(self, query, max_results=50, exact_match=True, engines=None, **kwargs):
        """
        Perform a unified search across multiple search engines.
        
        Args:
            query (str): The search query
            max_results (int): Maximum results per engine
            exact_match (bool): Whether to use exact string matching
            engines (list): List of engines to use ['google_api', 'duckduckgo', 'tavily', 'google_scraping']
            **kwargs: Additional parameters for specific engines
            
        Returns:
            dict: Results organized by search engine
        """
        
        # Auto-detect available engines if none specified
        if engines is None:
            engines = self.get_available_engines()
            if not engines:
                print("No search engines available! Please install dependencies.")
                return {}
        
        # Filter engines to only include available ones
        available_engines = self.get_available_engines()
        engines = [e for e in engines if e in available_engines]
        
        if not engines:
            print("None of the requested engines are available!")
            print(f"Available engines: {available_engines}")
            return {}
        
        all_results = {}
        
        print(f"\n=== UNIFIED SEARCH FOR: '{query}' ===")
        print(f"Engines: {engines}")
        print(f"Exact match: {exact_match}")
        
        # Google API Search
        if 'google_api' in engines:
            print("\n--- Google API Search ---")
            try:
                google_api_results = self.search_google_api(
                    query, 
                    max_results=max_results, 
                    exact_match=exact_match,
                    **kwargs
                )
                all_results['google_api'] = google_api_results
            except Exception as e:
                print(f"Google API search failed: {e}")
                all_results['google_api'] = []
        
        # DuckDuckGo Search
        if 'duckduckgo' in engines:
            print("\n--- DuckDuckGo Search ---")
            try:
                ddg_results = self.search_duckduckgo(
                    query, 
                    num_results=max_results, 
                    exact_match=exact_match
                )
                all_results['duckduckgo'] = ddg_results
            except Exception as e:
                print(f"DuckDuckGo search failed: {e}")
                all_results['duckduckgo'] = []
        
        # Tavily Search
        if 'tavily' in engines:
            print("\n--- Tavily Search ---")
            try:
                tavily_results = self.search_tavily(
                    query, 
                    max_results=max_results
                )
                all_results['tavily'] = tavily_results
            except Exception as e:
                print(f"Tavily search failed: {e}")
                all_results['tavily'] = []
        
        # Google Scraping (fallback)
        if 'google_scraping' in engines:
            print("\n--- Google Scraping Search ---")
            try:
                google_scraping_results = self.search_google_scraping(
                    query, 
                    num_results=max_results, 
                    exact_match=exact_match
                )
                all_results['google_scraping'] = google_scraping_results
            except Exception as e:
                print(f"Google scraping search failed: {e}")
                all_results['google_scraping'] = []
        
        # Summary
        total_unique_urls = len(self.deduplicate_results(all_results))
        print(f"\n=== SEARCH SUMMARY ===")
        for engine, results in all_results.items():
            print(f"{engine}: {len(results)} results")
        print(f"Total unique URLs: {total_unique_urls}")
        
        return all_results

    def deduplicate_results(self, results_dict):
        """
        Remove duplicate URLs from search results.
        
        Args:
            results_dict (dict): Dictionary of search results by engine
            
        Returns:
            list: Deduplicated list of URLs
        """
        all_urls = set()
        for engine_results in results_dict.values():
            all_urls.update(engine_results)
        return list(all_urls)

    def compare_search_results(self, query, old_results=None, engines=None):
        """
        Compare search results across different time periods and engines.
        
        Args:
            query (str): The search query
            old_results (list): Previous search results for comparison
            engines (list): List of engines to use
            
        Returns:
            dict: Comprehensive search results
        """
        print("=== COMPREHENSIVE SEARCH COMPARISON ===")
        
        # Try different time periods with Google API
        time_searches = [
            ("Current (no date filter)", None),
            ("Past day", "d1"),
            ("Past week", "w1"), 
            ("Past month", "m1"),
            ("Past 3 months", "m3"),
            ("Past 6 months", "m6"),
            ("Past year", "y1")
        ]
        
        all_found_urls = set()
        time_results = {}
        
        for desc, date_filter in time_searches:
            print(f"\n--- {desc} ---")
            results = self.search_google_api(
                query, 
                max_results=100, 
                date_restrict=date_filter
            )
            time_results[desc] = results
            all_found_urls.update(results)
            
            if old_results and results:
                overlap = set(results) & set(old_results)
                print(f"Overlap with old results: {len(overlap)}/{len(old_results)}")
            
            time.sleep(1)  # Be nice to the API
        
        # Also run unified search for comparison
        unified_results = self.unified_search(query, engines=engines)
        
        print(f"\nTotal unique URLs found across all time periods: {len(all_found_urls)}")
        
        return {
            'time_filtered': time_results,
            'unified': unified_results,
            'all_unique_urls': list(all_found_urls)
        }

    def get_available_engines(self):
        """
        Get a list of available search engines based on installed dependencies.
        
        Returns:
            list: Available search engine names
        """
        available = []
        
        if GOOGLE_API_AVAILABLE and self.google_api_key and self.google_cse_id:
            available.append('google_api')
        elif GOOGLE_API_AVAILABLE:
            print("Google API available but missing credentials")
            
        if DUCKDUCKGO_AVAILABLE:
            available.append('duckduckgo')
            
        if TAVILY_AVAILABLE:
            available.append('tavily')
            
        if GOOGLESEARCH_AVAILABLE and requests:
            available.append('google_scraping')
            
        return available
    
    def check_dependencies(self):
        """
        Print status of all dependencies and configurations.
        """
        print("=== SEARCH ENGINE DEPENDENCY STATUS ===")
        print(f"Google API Client: {'✓' if GOOGLE_API_AVAILABLE else '✗'}")
        print(f"Google API Key: {'✓' if self.google_api_key else '✗'}")
        print(f"Google CSE ID: {'✓' if self.google_cse_id else '✗'}")
        print(f"DuckDuckGo Search: {'✓' if DUCKDUCKGO_AVAILABLE else '✗'}")
        print(f"Tavily Search: {'✓' if TAVILY_AVAILABLE else '✗'}")
        print(f"Google Search (scraping): {'✓' if GOOGLESEARCH_AVAILABLE else '✗'}")
        print(f"Requests: {'✓' if requests else '✗'}")
        print(f"Available engines: {self.get_available_engines()}")
        print()

def process_url_by_type(url, output_folder="downloads/"):
    """
    Placeholder function for processing URLs based on their type.
    
    Note: This function requires the utils.file_converter module which 
    is not available in the current workspace. You'll need to implement
    or import the actual file conversion functions.
    
    Args:
        url (str): The URL to process
        output_folder (str): Folder to save downloaded files
        
    Returns:
        str: Path to the processed file or None if not implemented
    """
    print(f"URL processing not implemented for: {url}")
    print("To enable file processing, implement or import:")
    print("- download_xlsx, download_pdf, download_website_to_md")
    print("- convert_xlsx_to_md, convert_pdf_to_md")
    
    # Check file extension
    url_lower = url.lower()
    
    if url_lower.endswith('.xlsx') or url_lower.endswith('.xlsm'):
        print("Excel file detected - processing not implemented")
        return None
        
    elif url_lower.endswith('.pdf'):
        print("PDF file detected - processing not implemented")
        return None
        
    else:
        print("Website detected - processing not implemented")
        return None


def main():
    """
    Example usage of the unified search engine
    """
    search_engine = UnifiedSearchEngine()
    
    # Example searches
    test_queries = [
        "charles@charlesrivacollection.com",
        "machine learning research",
        "python programming tutorial"
    ]
    
    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"Testing query: {query}")
        print('='*60)
        
        # Basic unified search
        results = search_engine.unified_search(
            query, 
            max_results=20,
            engines=['google_api', 'duckduckgo']
        )
        
        # Get deduplicated results
        unique_urls = search_engine.deduplicate_results(results)
        
        print(f"\nFound {len(unique_urls)} unique URLs across all engines")
        
        # Show first few results
        if unique_urls:
            print("\nFirst 5 unique results:")
            for i, url in enumerate(unique_urls[:5], 1):
                print(f"{i}. {url}")


if __name__ == "__main__":
    main()
