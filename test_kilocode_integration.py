#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script to verify KiloCode integration with Warp2Api embeddings endpoint.
This simulates how KiloCode would interact with the embeddings API.
"""

import json
import requests
from typing import List, Dict, Any
import time

# Configuration from kilo-code-settings.json
CONFIG = {
    "endpoint": "http://localhost:4010/v1/embeddings",
    "api_key": "dummy_key",
    "model": "claude-4.1-opus"
}

def test_single_embedding():
    """Test single text embedding generation."""
    print("\n=== Testing Single Embedding ===")
    
    payload = {
        "input": "def calculate_sum(numbers): return sum(numbers)",
        "model": CONFIG["model"]
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": CONFIG["api_key"]
    }
    
    try:
        response = requests.post(CONFIG["endpoint"], json=payload, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        print(f"[OK] Successfully generated embedding")
        print(f"  - Model: {data['model']}")
        print(f"  - Embedding dimensions: {len(data['data'][0]['embedding'])}")
        print(f"  - Usage: {data['usage']['total_tokens']} tokens")
        return True
    except Exception as e:
        print(f"[FAIL] Failed: {e}")
        return False

def test_batch_embeddings():
    """Test batch embedding generation for multiple code snippets."""
    print("\n=== Testing Batch Embeddings ===")
    
    code_snippets = [
        "import React from 'react'; const Button = () => <button>Click</button>;",
        "async function fetchData(url) { const response = await fetch(url); return response.json(); }",
        "class UserService { constructor(db) { this.db = db; } async getUser(id) { return this.db.users.findById(id); } }"
    ]
    
    payload = {
        "input": code_snippets,
        "model": CONFIG["model"]
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": CONFIG["api_key"]
    }
    
    try:
        response = requests.post(CONFIG["endpoint"], json=payload, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        print(f"[OK] Successfully generated {len(data['data'])} embeddings")
        for i, embedding in enumerate(data['data']):
            print(f"  - Snippet {i+1}: {len(embedding['embedding'])} dimensions")
        print(f"  - Total tokens: {data['usage']['total_tokens']}")
        return True
    except Exception as e:
        print(f"[FAIL] Failed: {e}")
        return False

def test_code_similarity():
    """Test semantic similarity between code snippets."""
    print("\n=== Testing Code Similarity ===")
    
    # Two similar functions (both calculate sum)
    similar_code = [
        "def sum_numbers(nums): return sum(nums)",
        "function sumArray(arr) { return arr.reduce((a, b) => a + b, 0); }"
    ]
    
    # One different function (calculates product)
    different_code = "def multiply_numbers(nums): result = 1\n    for n in nums: result *= n\n    return result"
    
    all_code = similar_code + [different_code]
    
    payload = {
        "input": all_code,
        "model": CONFIG["model"]
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": CONFIG["api_key"]
    }
    
    try:
        response = requests.post(CONFIG["endpoint"], json=payload, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        embeddings = [d['embedding'] for d in data['data']]
        
        # Calculate cosine similarity
        def cosine_similarity(v1, v2):
            import math
            dot_product = sum(a * b for a, b in zip(v1, v2))
            magnitude1 = math.sqrt(sum(a * a for a in v1))
            magnitude2 = math.sqrt(sum(b * b for b in v2))
            return dot_product / (magnitude1 * magnitude2) if magnitude1 * magnitude2 != 0 else 0
        
        sim_similar = cosine_similarity(embeddings[0], embeddings[1])
        sim_different1 = cosine_similarity(embeddings[0], embeddings[2])
        sim_different2 = cosine_similarity(embeddings[1], embeddings[2])
        
        print(f"[OK] Similarity analysis complete")
        print(f"  - Similar functions (sum): {sim_similar:.4f}")
        print(f"  - Different functions (sum vs multiply): {sim_different1:.4f}")
        print(f"  - Different functions (sum JS vs multiply): {sim_different2:.4f}")
        
        if sim_similar > max(sim_different1, sim_different2):
            print("  [OK] Semantic similarity working correctly!")
            return True
        else:
            print("  [WARNING] Unexpected similarity scores")
            return False
            
    except Exception as e:
        print(f"[FAIL] Failed: {e}")
        return False

def test_large_code_chunk():
    """Test embedding generation for large code chunks."""
    print("\n=== Testing Large Code Chunk ===")
    
    # Simulate a large code file
    large_code = """
class DataProcessor:
    def __init__(self, config):
        self.config = config
        self.cache = {}
        
    def process_data(self, data):
        # Check cache first
        cache_key = self._generate_cache_key(data)
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        # Process the data
        result = []
        for item in data:
            processed = self._process_item(item)
            if processed:
                result.append(processed)
        
        # Cache the result
        self.cache[cache_key] = result
        return result
    
    def _process_item(self, item):
        # Apply transformations
        transformed = self._transform(item)
        
        # Validate
        if not self._validate(transformed):
            return None
            
        # Enrich with metadata
        enriched = self._enrich(transformed)
        return enriched
    
    def _transform(self, item):
        # Apply configured transformations
        for transformer in self.config.get('transformers', []):
            item = transformer(item)
        return item
    
    def _validate(self, item):
        # Run validation rules
        for validator in self.config.get('validators', []):
            if not validator(item):
                return False
        return True
    
    def _enrich(self, item):
        # Add metadata
        item['processed_at'] = time.time()
        item['processor_version'] = '1.0.0'
        return item
    
    def _generate_cache_key(self, data):
        import hashlib
        data_str = json.dumps(data, sort_keys=True)
        return hashlib.md5(data_str.encode()).hexdigest()
    """ * 3  # Repeat to make it larger
    
    payload = {
        "input": large_code,
        "model": CONFIG["model"]
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": CONFIG["api_key"]
    }
    
    try:
        start_time = time.time()
        response = requests.post(CONFIG["endpoint"], json=payload, headers=headers)
        response.raise_for_status()
        elapsed = time.time() - start_time
        
        data = response.json()
        print(f"[OK] Successfully processed large code chunk")
        print(f"  - Input length: {len(large_code)} characters")
        print(f"  - Tokens used: {data['usage']['total_tokens']}")
        print(f"  - Processing time: {elapsed:.2f}s")
        print(f"  - Embedding dimensions: {len(data['data'][0]['embedding'])}")
        return True
    except Exception as e:
        print(f"[FAIL] Failed: {e}")
        return False

def main():
    """Run all integration tests."""
    print("=" * 60)
    print("KiloCode Integration Tests for Warp2Api Embeddings")
    print("=" * 60)
    print(f"\nConfiguration:")
    print(f"  - Endpoint: {CONFIG['endpoint']}")
    print(f"  - Model: {CONFIG['model']}")
    print(f"  - API Key: {'*' * 8} (hidden)")
    
    tests = [
        ("Single Embedding", test_single_embedding),
        ("Batch Embeddings", test_batch_embeddings),
        ("Code Similarity", test_code_similarity),
        ("Large Code Chunk", test_large_code_chunk)
    ]
    
    results = []
    for name, test_func in tests:
        try:
            success = test_func()
            results.append((name, success))
        except Exception as e:
            print(f"\n[FAIL] Test '{name}' crashed: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary:")
    print("=" * 60)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for name, success in results:
        status = "[PASSED]" if success else "[FAILED]"
        print(f"  {status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n[SUCCESS] All tests passed! KiloCode integration is ready.")
        print("\nTo use with KiloCode:")
        print("1. Copy kilo-code-settings.json to your KiloCode config directory")
        print("2. Restart KiloCode extension")
        print("3. Enable code indexing in KiloCode settings")
        print("4. KiloCode will now use Warp2Api for embeddings!")
    else:
        print("\n[WARNING] Some tests failed. Please check the configuration.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)