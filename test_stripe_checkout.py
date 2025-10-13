#!/usr/bin/env python3
import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

API_BASE = "https://fa-axlypro-dev.azurewebsites.net/api"

def create_test_user():
    print("Step 1: Creating test user...")
    response = requests.post(
        f"{API_BASE}/auth/signup",
        json={
            "email": "testuser@example.com",
            "password": "Test123!@#"
        }
    )

    if response.status_code == 200:
        data = response.json()
        print(f"✅ User created: {data['user']['email']}")
        return data['access_token']
    elif response.status_code == 409:
        print("User already exists, trying login...")
        response = requests.post(
            f"{API_BASE}/auth/login",
            json={
                "email": "testuser@example.com",
                "password": "Test123!@#"
            }
        )
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Logged in: {data['user']['email']}")
            return data['access_token']

    print(f"❌ Failed: {response.status_code} - {response.text}")
    return None

def get_products():
    print("\nStep 2: Fetching products...")
    response = requests.get(f"{API_BASE}/subscriptions/products")

    if response.status_code == 200:
        data = response.json()
        if data['success'] and data['products']:
            product = data['products'][0]
            print(f"✅ Product: {product['name']}")
            print(f"   Price: {product['price']}")
            print(f"   Price ID: {product['stripe_price_id']}")
            return product['stripe_price_id']

    print(f"❌ Failed: {response.status_code} - {response.text}")
    return None

def create_checkout(token, price_id):
    print("\nStep 3: Creating checkout session...")
    response = requests.post(
        f"{API_BASE}/stripe/create-checkout",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        },
        json={
            "price_id": price_id,
            "success_url": "https://axly.pro/success",
            "cancel_url": "https://axly.pro/pricing"
        }
    )

    if response.status_code == 200:
        data = response.json()
        if data['success']:
            print(f"✅ Checkout URL: {data['checkout_url']}")
            print(f"\n🔗 Open this URL in your browser to complete test payment:")
            print(f"\n{data['checkout_url']}\n")
            print("Use test card: 4242 4242 4242 4242")
            print("Any future date, any 3-digit CVC")
            return data['checkout_url']

    print(f"❌ Failed: {response.status_code} - {response.text}")
    return None

def main():
    print("=== Stripe Checkout Test ===\n")

    token = create_test_user()
    if not token:
        sys.exit(1)

    price_id = get_products()
    if not price_id:
        sys.exit(1)

    checkout_url = create_checkout(token, price_id)
    if not checkout_url:
        sys.exit(1)

    print("\n✅ Test ready! Open the checkout URL above to complete payment.")

if __name__ == "__main__":
    main()
