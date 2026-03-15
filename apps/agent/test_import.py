import sys
import os

try:
    from google import genai
    from google.genai import types
    print("SUCCESS: google-genai imported correctly")
    print(f"genai file: {genai.__file__}")
except ImportError as e:
    print(f"FAILURE: {e}")
except Exception as e:
    print(f"ERROR: {e}")
