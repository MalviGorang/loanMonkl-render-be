#!/usr/bin/env python3
"""
Simple test script for authentication endpoints
"""

import requests
import json

BASE_URL = "http://127.0.0.1:8000/api"

def test_signup():
    """Test user signup"""
    print("Testing signup...")
    
    signup_data = {
        "email": "test@example.com",
        "password": "testpassword123",
        "full_name": "Test User",
        "mobile_number": "1234567890"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/auth/signup", json=signup_data)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_login():
    """Test user login"""
    print("\nTesting login...")
    
    login_data = {
        "email": "test@example.com",
        "password": "testpassword123"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/auth/login", json=login_data)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 200:
            token_data = response.json()
            return token_data.get("access_token")
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None

def test_me_endpoint(token):
    """Test /me endpoint with token"""
    print("\nTesting /me endpoint...")
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(f"{BASE_URL}/auth/me", headers=headers)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False

def main():
    print("=== Authentication System Test ===\n")
    
    # Test signup
    signup_success = test_signup()
    
    if signup_success:
        # Test login
        token = test_login()
        
        if token:
            # Test /me endpoint
            me_success = test_me_endpoint(token)
            
            if me_success:
                print("\n✅ All tests passed! Authentication system is working.")
            else:
                print("\n❌ /me endpoint test failed.")
        else:
            print("\n❌ Login test failed.")
    else:
        print("\n❌ Signup test failed.")
    
    print("\n=== Test Complete ===")

if __name__ == "__main__":
    main() 