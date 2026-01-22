import sys
import os
from dotenv import load_dotenv

print(f"Python version: {sys.version}")

try:
    print("Testing imports...")
    import browser_use
    print(f"  - browser_use: {browser_use.__version__ if hasattr(browser_use, '__version__') else 'installed'}")
    
    from browser_use.browser import Browser, BrowserConfig
    print("  - browser_use.browser import successful")

    import langchain_google_vertexai
    print("  - langchain_google_vertexai import successful")
    
    import playwright
    print("  - playwright import successful")
    
    import yaml
    print("  - pyyaml import successful")
    
    load_dotenv()
    print("  - python-dotenv import successful")
    
    print("\nEnvironment check:")
    print(f"  - GOOGLE_CLOUD_PROJECT: {os.getenv('GOOGLE_CLOUD_PROJECT', 'Not Set')}")
    print(f"  - GOOGLE_CLOUD_REGION: {os.getenv('GOOGLE_CLOUD_REGION', 'Not Set')}")
    print(f"  - GEMINI_MODEL_NAME: {os.getenv('GEMINI_MODEL_NAME', 'Not Set')}")

    print("\n✅ Setup seems correct!")

except ImportError as e:
    print(f"\n❌ Import Error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"\n❌ Unexpected Error: {e}")
    sys.exit(1)
