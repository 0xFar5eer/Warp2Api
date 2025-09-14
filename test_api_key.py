#!/usr/bin/env python
"""
Test script to verify API key authentication behavior
Tests different API_KEY configurations in .env file
"""

import os
import sys
import time
import subprocess
import requests

def update_env_file(api_key_value):
    """Update the API_KEY value in .env file"""
    env_path = ".env"
    with open(env_path, 'r') as f:
        lines = f.readlines()
    
    with open(env_path, 'w') as f:
        for line in lines:
            if line.startswith("API_KEY="):
                if api_key_value is None:
                    # Empty API key
                    f.write("API_KEY=\n")
                else:
                    # Set specific API key
                    f.write("API_KEY=" + str(api_key_value) + "\n")
            else:
                f.write(line)

def restart_docker_compose():
    """Restart docker compose services"""
    print("Restarting Docker Compose...")
    try:
        # Stop services
        subprocess.check_call(["docker-compose", "down"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # Start services
        subprocess.check_call(["docker-compose", "up", "-d"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # Wait for services to be ready
        print("Waiting for services to start...")
        time.sleep(10)  # Give services time to fully start
        return True
    except subprocess.CalledProcessError as e:
        print("Failed to restart Docker Compose: " + str(e))
        return False

def test_api_endpoint(api_key=None, port=4009):
    """Test API endpoint with or without API key"""
    url = "http://localhost:" + str(port) + "/api/auth/status"
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        return response.status_code, response.text
    except requests.RequestException as e:
        return 0, str(e)

def run_test_scenario(scenario_name, env_api_key, request_api_key, expected_status):
    """Run a single test scenario"""
    print("\n" + "="*60)
    print("Test Scenario: " + scenario_name)
    print("   ENV API_KEY: " + ('(empty)' if env_api_key is None else env_api_key))
    print("   Request API_KEY: " + ('(none)' if request_api_key is None else request_api_key))
    print("   Expected Status: " + str(expected_status))
    print("="*60)
    
    # Update .env file
    print("Setting API_KEY in .env to: " + ('(empty)' if env_api_key is None else env_api_key))
    update_env_file(env_api_key)
    
    # Restart Docker Compose
    if not restart_docker_compose():
        return False
    
    # Test both ports
    ports = [4009, 4010]
    all_passed = True
    
    for port in ports:
        print("\nTesting port " + str(port) + "...")
        status_code, response = test_api_endpoint(request_api_key, port)
        
        if status_code == expected_status:
            print("Port " + str(port) + ": PASSED (Got expected " + str(status_code) + ")")
        else:
            print("Port " + str(port) + ": FAILED (Expected " + str(expected_status) + ", got " + str(status_code) + ")")
            print("   Response: " + response[:200])
            all_passed = False
    
    return all_passed

def main():
    print("API Key Authentication Test Suite")
    print("=====================================")
    
    results = []
    
    # Test 1: Empty API_KEY in .env, no key in request -> Should succeed (200)
    results.append(run_test_scenario(
        "Empty API_KEY, no auth required",
        None,
        None,
        200
    ))
    
    # Test 2: Set API_KEY in .env, no key in request -> Should fail (401)
    results.append(run_test_scenario(
        "API_KEY set, no key provided",
        "test_secret_key_123",
        None,
        401
    ))
    
    # Test 3: Set API_KEY in .env, wrong key in request -> Should fail (401)
    results.append(run_test_scenario(
        "API_KEY set, wrong key provided",
        "test_secret_key_123",
        "wrong_key",
        401
    ))
    
    # Test 4: Set API_KEY in .env, correct key in request -> Should succeed (200)
    results.append(run_test_scenario(
        "API_KEY set, correct key provided",
        "test_secret_key_123",
        "test_secret_key_123",
        200
    ))
    
    # Test 5: Back to empty API_KEY -> Should succeed without auth (200)
    results.append(run_test_scenario(
        "Reset to empty API_KEY",
        None,
        None,
        200
    ))
    
    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(results)
    total = len(results)
    
    for i, result in enumerate(results):
        status = "PASSED" if result else "FAILED"
        print("Test " + str(i + 1) + ": " + status)
    
    print("\nOverall: " + str(passed) + "/" + str(total) + " tests passed")
    
    if passed == total:
        print("All tests passed!")
        return 0
    else:
        print("Some tests failed. Please check the output above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())