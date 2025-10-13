#!/usr/bin/env python3
import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("ERROR: DATABASE_URL not found in .env")
    sys.exit(1)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import User, UserRole, UserTier, StripeSubscription
from auth.utils import hash_password
import uuid

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

# Test account credentials
TEST_EMAIL = "testuser@axly.app"
TEST_PASSWORD = "TestPro2024!"

print("=== Creating Test Account ===\n")

# Check if user already exists
existing_user = session.query(User).filter(User.email == TEST_EMAIL).first()

if existing_user:
    print(f"✅ Test user already exists: {TEST_EMAIL}")
    print(f"   User ID: {existing_user.id}")
    print(f"   Tier: {existing_user.tier.value}")
    
    # Update to premium if not already
    if existing_user.tier != UserTier.PREMIUM:
        existing_user.tier = UserTier.PREMIUM
        session.commit()
        print("   Updated to PREMIUM tier")
else:
    # Create new user
    user = User(
        email=TEST_EMAIL,
        password_hash=hash_password(TEST_PASSWORD),
        role=UserRole.USER,
        tier=UserTier.PREMIUM,
        created_via_receipt=False
    )
    session.add(user)
    session.flush()
    
    print(f"✅ Created test user: {TEST_EMAIL}")
    print(f"   User ID: {user.id}")
    print(f"   Tier: {user.tier.value}")
    
    # Create a fake premium subscription (1 year validity)
    subscription = StripeSubscription(
        user_id=user.id,
        stripe_customer_id="test_customer_" + str(uuid.uuid4())[:8],
        stripe_subscription_id="test_sub_" + str(uuid.uuid4())[:8],
        status="active",
        current_period_end=datetime.utcnow() + timedelta(days=365)
    )
    session.add(subscription)
    
    session.commit()
    print("   Added 1-year premium subscription")

print("\n" + "="*50)
print("TEST ACCOUNT CREDENTIALS:")
print("="*50)
print(f"Email:    {TEST_EMAIL}")
print(f"Password: {TEST_PASSWORD}")
print("="*50)
print("\nThis account has:")
print("  ✓ PREMIUM tier access")
print("  ✓ All features unlocked")
print("  ✓ Valid subscription for 1 year")
print("\nShare these credentials with your testers!")

session.close()
