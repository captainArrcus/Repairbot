#!/usr/bin/env python3
"""
Example usage of the Unified Search Engine

This script demonstrates how to use the unified search functionality
with different configurations and fallback options.
"""

try:
    # Try relative imports first (when used as a module)
    from .unified_search import UnifiedSearchEngine, process_url_by_type
except ImportError:
    # Fall back to absolute imports (when run directly)
    from unified_search import UnifiedSearchEngine, process_url_by_type


def basic_search_example():
    """
    Basic search example with automatic engine detection
    """
    print("=== BASIC SEARCH EXAMPLE ===")
    
    search_engine = UnifiedSearchEngine()
    
    # Check what's available
    search_engine.check_dependencies()
    
    query = "charles@charlesrivacollection.com"
    
    # Perform unified search with auto-detection
    results = search_engine.unified_search(query, max_results=20)
    
    # Get all unique URLs
    unique_urls = search_engine.deduplicate_results(results)
    
    print(f"\nFound {len(unique_urls)} unique URLs")
    if unique_urls:
        print("\nFirst 5 results:")
        for i, url in enumerate(unique_urls[:5], 1):
            print(f"{i}. {url}")
    
    return results


def tavily_detailed_search_example():
    """
    Example showing Tavily's detailed search capabilities
    """
    print("\n=== TAVILY DETAILED SEARCH EXAMPLE ===")
    
    search_engine = UnifiedSearchEngine()
    
    if 'tavily' not in search_engine.get_available_engines():
        print("Tavily search not available (missing API key or package)")
        return None
    
    query = "art authentication techniques"
    
    # Get detailed results with content
    detailed_results = search_engine.search_tavily_detailed(
        query,
        num_results=5,
        search_depth="advanced"
    )
    
    print(f"\nDetailed Tavily Results ({len(detailed_results)} found):")
    for i, result in enumerate(detailed_results, 1):
        print(f"\n{i}. {result['title']}")
        print(f"   URL: {result['url']}")
        print(f"   Score: {result['score']:.2f}")
        print(f"   Content: {result['content'][:150]}...")
    
    return detailed_results


def domain_filtered_search_example():
    """
    Example of domain-filtered search using Tavily
    """
    print("\n=== DOMAIN FILTERED SEARCH EXAMPLE ===")
    
    search_engine = UnifiedSearchEngine()
    
    if 'tavily' not in search_engine.get_available_engines():
        print("Tavily search not available for domain filtering")
        return None
    
    query = "machine learning tutorials"
    
    # Search with domain filtering
    results = search_engine.search_tavily_detailed(
        query,
        num_results=5,
        include_domains=["github.com", "stackoverflow.com", "medium.com", "towardsdatascience.com"]
    )
    
    print(f"\nFiltered Results ({len(results)} found):")
    for i, result in enumerate(results, 1):
        print(f"{i}. {result['title']}")
        print(f"   URL: {result['url']}")
        print(f"   Domain: {result['url'].split('/')[2]}")
    
    return results


def advanced_search_example():
    """
    Advanced search with specific parameters
    """
    print("\n=== ADVANCED SEARCH EXAMPLE ===")
    
    search_engine = UnifiedSearchEngine()
    
    query = "machine learning research"
    
    # Search with specific time filter (Google API only)
    if 'google_api' in search_engine.get_available_engines():
        results = search_engine.unified_search(
            query,
            max_results=30,
            engines=['google_api'],  # Only use Google API
            date_restrict='m1',      # Past month only
            country='us',            # US results
            language='lang_en',      # English only
            sort_by_date=True        # Sort by date
        )
    else:
        print("Google API not available, using available engines...")
        results = search_engine.unified_search(query, max_results=30)
    
    return results


def fallback_search_example():
    """
    Example showing fallback to different engines
    """
    print("\n=== FALLBACK SEARCH EXAMPLE ===")
    
    search_engine = UnifiedSearchEngine()
    
    query = "python programming tutorial"
    
    # Try preferred engines first, fall back to others
    available_engines = search_engine.get_available_engines()
    preferred_engines = [engine for engine in ['tavily', 'google_api', 'duckduckgo'] if engine in available_engines]
    fallback_engines = [engine for engine in ['google_scraping'] if engine in available_engines]
    
    results = search_engine.unified_search(
        query,
        max_results=25,
        engines=preferred_engines
    )
    
    # If no results, try fallback
    unique_urls = search_engine.deduplicate_results(results)
    
    if not unique_urls and fallback_engines:
        print("No results from preferred engines, trying fallback...")
        fallback_results = search_engine.unified_search(
            query,
            max_results=25,
            engines=fallback_engines
        )
        results.update(fallback_results)
        unique_urls = search_engine.deduplicate_results(results)
    
    print(f"Total unique URLs: {len(unique_urls)}")
    return results


def engine_comparison_example():
    """
    Example comparing different search engines for the same query
    """
    print("\n=== ENGINE COMPARISON EXAMPLE ===")
    
    search_engine = UnifiedSearchEngine()
    
    query = "art provenance research"
    available_engines = search_engine.get_available_engines()
    
    if not available_engines:
        print("No search engines available")
        return None
    
    print(f"Comparing engines: {available_engines}")
    
    # Test each engine individually
    individual_results = {}
    
    for engine in available_engines:
        print(f"\n--- Testing {engine.upper()} ---")
        
        if engine == 'google_api':
            results = search_engine.search_google_api(query, max_results=5)
        elif engine == 'duckduckgo':
            results = search_engine.search_duckduckgo(query, num_results=5)
        elif engine == 'tavily':
            results = search_engine.search_tavily(query, num_results=5)
        elif engine == 'google_scraping':
            results = search_engine.search_google_scraping(query, num_results=5)
        else:
            results = []
        
        individual_results[engine] = results
        print(f"Found {len(results)} results")
        
        # Show first few results
        for i, url in enumerate(results[:2], 1):
            print(f"  {i}. {url}")
    
    # Compare overlaps
    print("\n--- OVERLAP ANALYSIS ---")
    all_urls = set()
    for engine, urls in individual_results.items():
        all_urls.update(urls)
    
    print(f"Total unique URLs across all engines: {len(all_urls)}")
    
    # Show engine-specific vs shared results
    for engine, urls in individual_results.items():
        unique_to_engine = set(urls) - set().union(*[set(other_urls) for other_engine, other_urls in individual_results.items() if other_engine != engine])
        print(f"{engine}: {len(urls)} results, {len(unique_to_engine)} unique to this engine")
    
    return individual_results


def url_processing_example():
    """
    Example of URL processing workflow
    """
    print("\n=== URL PROCESSING EXAMPLE ===")
    
    search_engine = UnifiedSearchEngine()
    
    query = "art authentication PDF"
    
    # Get some search results
    results = search_engine.unified_search(query, max_results=10)
    unique_urls = search_engine.deduplicate_results(results)
    
    if not unique_urls:
        print("No URLs found to process")
        return None
    
    print(f"Processing first 3 URLs from {len(unique_urls)} found...")
    
    processed_files = []
    for i, url in enumerate(unique_urls[:3], 1):
        print(f"\n{i}. Processing: {url}")
        
        try:
            processed_file = process_url_by_type(url)
            if processed_file:
                processed_files.append(processed_file)
                print(f"   ✓ Processed file: {processed_file}")
            else:
                print(f"   ✗ Could not process URL")
        except Exception as e:
            print(f"   ✗ Error processing URL: {e}")
    
    print(f"\nSuccessfully processed {len(processed_files)} files")
    return processed_files


def main():
    """
    Run all examples
    """
    print("Unified Search Engine Examples")
    print("=" * 50)
    
    try:
        # Basic search
        basic_results = basic_search_example()
        
        # Tavily detailed search
        tavily_detailed_results = tavily_detailed_search_example()
        
        # Domain filtered search
        domain_filtered_results = domain_filtered_search_example()
        
        # Advanced search (only if Google API is available)
        advanced_results = advanced_search_example()
        
        # Fallback search
        fallback_results = fallback_search_example()
        
        # Engine comparison
        comparison_results = engine_comparison_example()
        
        # URL processing
        processed_files = url_processing_example()
        
        print("\n" + "=" * 50)
        print("All examples completed!")
        
    except KeyboardInterrupt:
        print("\nSearch interrupted by user")
    except Exception as e:
        print(f"\nError during search: {e}")


if __name__ == "__main__":
    main()
