#!/usr/bin/env python3
"""
Setup script for the Unified Search Engine

This script helps set up the required dependencies and environment variables.
"""

import subprocess
import sys
import os


def install_dependencies():
    """
    Install required dependencies
    """
    print("Installing search engine dependencies...")
    
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "-r", "requirements_search.txt"
        ])
        print("✓ Dependencies installed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to install dependencies: {e}")
        return False


def check_environment():
    """
    Check if required environment variables are set
    """
    print("\nChecking environment variables...")
    
    required_vars = {
        "GOOGLE_SEARCH_API_KEY": "Google Custom Search API Key",
        "GOOGLE_CSE_ID": "Google Custom Search Engine ID"
    }
    
    missing_vars = []
    
    for var, description in required_vars.items():
        if os.getenv(var):
            print(f"✓ {var} is set")
        else:
            print(f"✗ {var} is missing ({description})")
            missing_vars.append(var)
    
    if missing_vars:
        print(f"\nTo set up Google API access:")
        print("1. Go to https://console.developers.google.com/")
        print("2. Create a new project or select existing one")
        print("3. Enable the Custom Search API")
        print("4. Create credentials (API Key)")
        print("5. Create a Custom Search Engine at https://cse.google.com/")
        print("6. Set environment variables in .env file:")
        print()
        for var in missing_vars:
            print(f"{var}=your_{var.lower()}_here")
        print()
        
        return False
    
    return True


def test_search():
    """
    Test the search functionality
    """
    print("\nTesting search functionality...")
    
    try:
        from art_research.search.unified_search import UnifiedSearchEngine
        
        search_engine = UnifiedSearchEngine()
        search_engine.check_dependencies()
        
        available_engines = search_engine.get_available_engines()
        
        if available_engines:
            print(f"✓ Available search engines: {available_engines}")
            
            # Quick test search
            print("\nPerforming test search...")
            results = search_engine.unified_search(
                "test query", 
                max_results=5,
                engines=available_engines[:1]  # Use just one engine for test
            )
            
            if any(results.values()):
                print("✓ Search test successful!")
            else:
                print("⚠ Search test returned no results (this might be normal)")
                
        else:
            print("✗ No search engines available")
            return False
            
    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False
    except Exception as e:
        print(f"✗ Test failed: {e}")
        return False
    
    return True


def main():
    """
    Main setup function
    """
    print("Unified Search Engine Setup")
    print("=" * 40)
    
    # Check if we're in the right directory
    if not os.path.exists("requirements_search.txt"):
        print("✗ requirements_search.txt not found!")
        print("Please run this script from the art_research directory.")
        return False
    
    # Install dependencies
    if not install_dependencies():
        return False
    
    # Check environment
    env_ok = check_environment()
    
    # Test functionality
    if not test_search():
        print("\n⚠ Setup completed but testing failed.")
        print("You may need to configure API credentials.")
        return False
    
    if env_ok:
        print("\n✓ Setup completed successfully!")
        print("You can now use the unified search engine.")
    else:
        print("\n⚠ Setup completed but environment variables need configuration.")
        print("Some search engines may not work without proper API credentials.")
    
    print("\nTo get started:")
    print("python search_examples.py")
    
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
