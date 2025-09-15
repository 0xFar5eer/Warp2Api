#!/usr/bin/env python3
"""Simple test for the /v1/embeddings endpoint"""

import json
import sys

try:
    import requests
except ImportError:
    print("Installing requests...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

def test_embeddings():
    """Test the embeddings endpoint"""
    
    base_url = "http://localhost:4010"
    api_key = "dummy_key"  # From your .env file
    
    # Prepare request
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    payload = {
        "input": "def hello_world():\n    print('Hello, World!')",
        "model": "claude-4.1-opus"
    }
    
    print("Testing /v1/embeddings endpoint...")
    print(f"URL: {base_url}/v1/embeddings")
    print(f"API Key: {api_key}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    print("-" * 50)
    
    try:
        response = requests.post(
            f"{base_url}/v1/embeddings",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Success!")
            print(f"Response object: {data.get('object')}")
            print(f"Model: {data.get('model')}")
            
            if 'data' in data and len(data['data']) > 0:
                embedding = data['data'][0]['embedding']
                print(f"Embedding dimensions: {len(embedding)}")
                print(f"First 5 values: {embedding[:5]}")
                print(f"Usage: {data.get('usage')}")
            
            return True
        else:
            print(f"❌ Failed with status {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError as e:
        print(f"❌ Connection error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    success = test_embeddings()
    sys.exit(0 if success else 1)