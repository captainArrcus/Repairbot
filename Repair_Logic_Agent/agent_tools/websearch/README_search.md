# Unified Search Engine

A comprehensive search system that combines multiple search engines and processing capabilities for research and data collection.

## Features

- **Multiple Search Engines**: Google API, DuckDuckGo, Tavily, and Google Scraping (fallback)
- **Advanced Filtering**: Date ranges, countries, languages, safe search
- **Exact String Matching**: Wrap queries in quotes for precise searches
- **Detailed Results**: Rich content and metadata (Tavily)
- **Result Deduplication**: Automatically remove duplicate URLs
- **Domain Filtering**: Include/exclude specific domains (Tavily)
- **Graceful Fallbacks**: Handle missing dependencies and API failures
- **File Processing**: Support for Excel, PDF, and website content (placeholder)
- **Rate Limiting**: Built-in delays to respect API limits

## Quick Start

1. **Install Dependencies**:
   ```bash
   python setup_search.py
   ```

2. **Configure Environment** (optional for enhanced features):
   Create a `.env` file with:
   ```env
   GOOGLE_SEARCH_API_KEY=your_google_api_key_here
   GOOGLE_CSE_ID=your_google_cse_id_here
   TAVILY_API_KEY=your_tavily_api_key_here
   ```

3. **Run Examples**:
   ```bash
   python search_examples.py
   ```

## Basic Usage

```python
from unified_search import UnifiedSearchEngine

# Create search engine instance
search_engine = UnifiedSearchEngine()

# Check available engines
search_engine.check_dependencies()

# Basic search across all available engines
results = search_engine.unified_search("your search query")

# Get unique URLs
unique_urls = search_engine.deduplicate_results(results)
print(f"Found {len(unique_urls)} unique results")
```

## Advanced Usage

### Specific Search Engines

```python
# Use only Google API with advanced filtering
results = search_engine.unified_search(
    "machine learning research",
    max_results=50,
    engines=['google_api'],
    date_restrict='m1',      # Past month
    country='us',            # US results
    language='lang_en',      # English only
    sort_by_date=True        # Sort by date
)
```

### DuckDuckGo Search

```python
# Use DuckDuckGo for privacy-focused search
results = search_engine.unified_search(
    "privacy tools",
    engines=['duckduckgo'],
    max_results=30
)
```

### Tavily Search with Detailed Results

```python
# Get detailed search results with content, titles, and scores
detailed_results = search_engine.search_tavily_detailed(
    "artificial intelligence research",
    num_results=5,
    search_depth="advanced"  # "basic" or "advanced"
)

for result in detailed_results:
    print(f"Title: {result['title']}")
    print(f"URL: {result['url']}")
    print(f"Score: {result['score']}")
    print(f"Content: {result['content'][:200]}...")
```

### Domain Filtering with Tavily

```python
# Include specific domains
results = search_engine.search_tavily(
    "machine learning tutorials",
    num_results=10,
    include_domains=["github.com", "stackoverflow.com", "medium.com"]
)

# Exclude specific domains
results = search_engine.search_tavily(
    "python programming",
    num_results=10,
    exclude_domains=["ads.com", "spam.com"]
)
```

### Fallback Search

```python
# Try Google API first, fall back to scraping
preferred = search_engine.unified_search(
    "rare search term",
    engines=['google_api']
)

if not search_engine.deduplicate_results(preferred):
    fallback = search_engine.unified_search(
        "rare search term",
        engines=['google_scraping']
    )
```

## Search Engine Options

### Google Custom Search API
- **Pros**: Reliable, fast, advanced filtering options
- **Cons**: Requires API key, daily quota limits
- **Setup**: Get API key from Google Cloud Console

### DuckDuckGo
- **Pros**: No API key required, privacy-focused
- **Cons**: Fewer filtering options, rate limits
- **Setup**: No configuration needed

### Tavily
- **Pros**: Detailed results with content, flexible domain filtering
- **Cons**: Requires API key, limited free tier
- **Setup**: Get API key from Tavily

### Google Scraping (Fallback)
- **Pros**: No API key required, works when API fails
- **Cons**: Slower, less reliable, may break with Google changes
- **Setup**: No configuration needed

## Configuration

### Environment Variables

```env
# Google API Configuration (optional but recommended)
GOOGLE_SEARCH_API_KEY=your_google_api_key
GOOGLE_CSE_ID=your_custom_search_engine_id

# Tavily API Configuration (optional)
TAVILY_API_KEY=your_tavily_api_key
```

### Getting Google API Credentials

1. Go to [Google Cloud Console](https://console.developers.google.com/)
2. Create or select a project
3. Enable the "Custom Search API"
4. Create an API key in Credentials
5. Create a Custom Search Engine at [Google CSE](https://cse.google.com/)
6. Note your Search Engine ID

### Getting Tavily API Credentials

1. Go to [Tavily API](https://tavily.com/)
2. Sign up for an account
3. Get your API key from the dashboard
4. Add it to your `.env` file as `TAVILY_API_KEY`

## API Reference

### UnifiedSearchEngine Class

#### Methods

- `search_google_api(query, max_results=100, **filters)` - Google API search
- `search_duckduckgo(query, num_results=10, exact_match=True)` - DuckDuckGo search  
- `search_google_scraping(query, num_results=10, **options)` - Google scraping
- `unified_search(query, max_results=50, engines=None, **kwargs)` - Multi-engine search
- `deduplicate_results(results_dict)` - Remove duplicate URLs
- `compare_search_results(query, old_results=None)` - Time-based comparison
- `get_available_engines()` - List available search engines
- `check_dependencies()` - Check installation status
- `search_tavily(query, num_results=10, search_depth="basic", include_domains=None, exclude_domains=None)` - Tavily search
- `search_tavily_detailed(query, num_results=10, search_depth="basic", include_domains=None, exclude_domains=None)` - Tavily detailed search

#### Parameters

**Common Parameters:**
- `query` (str): Search query
- `max_results` (int): Maximum results to return
- `exact_match` (bool): Use exact string matching (wrap in quotes)
- `engines` (list): Specific engines to use

**Google API Filters:**
- `date_restrict` (str): 'd1', 'w1', 'm1', 'm3', 'm6', 'y1'
- `country` (str): Country code ('us', 'uk', 'de', etc.)
- `language` (str): Language code ('lang_en', 'lang_de', etc.)
- `safe_search` (str): 'off', 'medium', 'high'
- `sort_by_date` (bool): Sort by date instead of relevance

## Dependencies

### Required
- `requests` - HTTP requests
- `python-dotenv` - Environment variable loading

### Optional (by search engine)
- `google-api-python-client` - Google API access
- `googlesearch-python` - Google scraping fallback
- `duckduckgo-search` - DuckDuckGo API access
- `tavily-python` - Tavily API access

### File Processing (placeholder)
- `pandas` - Excel file processing
- `PyPDF2` - PDF processing
- `beautifulsoup4` - Web content extraction

## Error Handling

The system gracefully handles:
- Missing dependencies (shows warnings, disables affected features)
- API quota exceeded (falls back to other engines)
- Network errors (retries with exponential backoff)
- Invalid queries (returns empty results)

## Rate Limiting

- **Google API**: 0.1 seconds between pagination requests
- **Google Scraping**: 2-5 seconds between requests, exponential backoff on errors
- **DuckDuckGo**: Built-in rate limiting

## Examples

See `search_examples.py` for comprehensive usage examples:

- Basic search with auto-detection
- Advanced search with filtering
- Tavily detailed results and domain filtering
- Fallback engine strategies  
- Time-based result comparison

## Troubleshooting

### No Search Engines Available
```bash
python setup_search.py  # Install dependencies
```

### Google API Errors
- Check API key in `.env` file
- Verify Custom Search Engine ID
- Check daily quota usage

### Tavily API Errors
- Check API key in `.env` file
- Verify Tavily account status
- Check API usage limits

### Import Errors
```bash
pip install -r requirements_search.txt
```

### Rate Limiting
- Add delays between searches
- Use fewer engines simultaneously
- Check API quotas

## File Structure

```
art_research/
├── unified_search.py          # Main search engine
├── search_examples.py         # Usage examples
├── setup_search.py           # Setup script
├── requirements_search.txt   # Dependencies
├── README_search.md         # This file
├── search.py               # Original search functions
└── search_tools.py         # Original Google API tools
```

## Migration from Original Files

The unified search engine combines functionality from:
- `search.py` - Basic search functions and file processing
- `search_tools.py` - Advanced Google API features

### Key Improvements
- Better error handling and fallbacks
- Automatic engine detection
- Unified API across all search engines
- Enhanced rate limiting and retry logic
- Comprehensive result deduplication

## License

This module is part of the Operation Platypus microservices project.
