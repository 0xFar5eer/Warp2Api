#!/usr/bin/env python3
"""
Test script for the /v1/embeddings endpoint
"""

import json
import sys
try:
    import requests
except ImportError:
    print("Installing requests...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

try:
    import numpy as np
except ImportError:
    print("Installing numpy...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "numpy"])
    import numpy as np

from typing import List, Dict, Any


def test_embeddings_endpoint(base_url="http://localhost:4010", api_key=None):
    """Test the embeddings endpoint with various inputs"""
    
    # Prepare headers
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    # Test cases
    test_cases = [
        {
            "name": "Single text input",
            "payload": {
                "input": "def calculate_sum(a, b):\n    return a + b",
                "model": "claude-4.1-opus"
            }
        },
        {
            "name": "Multiple text inputs",
            "payload": {
                "input": [
                    "import numpy as np",
                    "class DataProcessor:\n    def __init__(self):\n        pass",
                    "async function fetchData() { return await fetch('/api/data'); }"
                ],
                "model": "claude-4.1-opus"
            }
        },
        {
            "name": "With custom dimensions",
            "payload": {
                "input": "SELECT * FROM users WHERE id = ?",
                "model": "claude-4.1-opus",
                "dimensions": 768
            }
        }
    ]
    
    print("=" * 60)
    print("Testing /v1/embeddings endpoint")
    print("=" * 60)
    print(f"Base URL: {base_url}")
    print(f"API Key: {'Set' if api_key else 'Not set'}")
    print()
    
    for test_case in test_cases:
        print(f"\nTest: {test_case['name']}")
        print("-" * 40)
        
        try:
            # Send request
            response = requests.post(
                f"{base_url}/v1/embeddings",
                headers=headers,
                json=test_case["payload"],
                timeout=30
            )
            
            # Check response
            if response.status_code == 200:
                data = response.json()
                
                # Validate response structure
                assert "object" in data, "Missing 'object' field"
                assert data["object"] == "list", f"Expected object='list', got '{data['object']}'"
                assert "data" in data, "Missing 'data' field"
                assert "model" in data, "Missing 'model' field"
                assert "usage" in data, "Missing 'usage' field"
                
                # Check embeddings
                embeddings = data["data"]
                input_data = test_case["payload"]["input"]
                expected_count = 1 if isinstance(input_data, str) else len(input_data)
                
                assert len(embeddings) == expected_count, \
                    f"Expected {expected_count} embeddings, got {len(embeddings)}"
                
                # Validate each embedding
                for i, emb in enumerate(embeddings):
                    assert "object" in emb, f"Embedding {i}: Missing 'object' field"
                    assert emb["object"] == "embedding", \
                        f"Embedding {i}: Expected object='embedding', got '{emb['object']}'"
                    assert "embedding" in emb, f"Embedding {i}: Missing 'embedding' field"
                    assert "index" in emb, f"Embedding {i}: Missing 'index' field"
                    assert emb["index"] == i, f"Embedding {i}: Index mismatch"
                    
                    # Check embedding vector
                    vector = emb["embedding"]
                    expected_dim = test_case["payload"].get("dimensions", 1536)
                    assert len(vector) == expected_dim, \
                        f"Embedding {i}: Expected {expected_dim} dimensions, got {len(vector)}"
                    
                    # Verify it's normalized (unit vector)
                    norm = np.linalg.norm(vector)
                    assert abs(norm - 1.0) < 0.01, \
                        f"Embedding {i}: Not normalized (norm={norm})"
                
                print(f"✅ Success!")
                print(f"   - Generated {len(embeddings)} embedding(s)")
                print(f"   - Dimensions: {len(embeddings[0]['embedding'])}")
                print(f"   - Token usage: {data['usage']}")
                
            else:
                print(f"❌ Failed with status {response.status_code}")
                print(f"   Error: {response.text}")
                
        except Exception as e:
            print(f"❌ Exception: {e}")
    
    print("\n" + "=" * 60)
    print("Testing complete!")
    print("=" * 60)


def test_with_kilocode_settings():
    """Test with KiloCode-like settings"""
    
    print("\n" + "=" * 60)
    print("Testing with KiloCode indexing configuration")
    print("=" * 60)
    
    # Simulate KiloCode's code indexing request
    code_sample = '''
    export class TodoItem {
        constructor(public id: string, public text: string, public completed: boolean) {}
        
        toggle() {
            this.completed = !this.completed;
        }
    }
    '''
    
    payload = {
        "input": code_sample,
        "model": "claude-4.1-opus",
        "dimensions": 1536,
        "encoding_format": "float"
    }
    
    headers = {"Content-Type": "application/json"}
    
    try:
        response = requests.post(
            "http://localhost:4010/v1/embeddings",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            embedding = data["data"][0]["embedding"]
            
            print(f"✅ Successfully generated embedding for code indexing")
            print(f"   - Vector dimensions: {len(embedding)}")
            print(f"   - First 10 values: {embedding[:10]}")
            print(f"   - Norm: {np.linalg.norm(embedding):.6f}")
            print(f"\nThis embedding can be stored in Qdrant for similarity search")
            
        else:
            print(f"❌ Failed: {response.status_code} - {response.text}")
            
    except Exception as e:
        print(f"❌ Exception: {e}")


if __name__ == "__main__":
    import sys
    
    # Check if API key is provided
    api_key = None
    if len(sys.argv) > 1:
        api_key = sys.argv[1]
    
    # Run tests
    test_embeddings_endpoint(api_key=api_key)
    test_with_kilocode_settings()