# Stripe Integration Setup Guide

## Environment Variables Required

Add these to your Azure Function App Configuration or `.env` file:

```bash
# Stripe API Keys (Get from Stripe Dashboard > Developers > API Keys)
STRIPE_SECRET_KEY=sk_test_51...  # Test mode key for now
STRIPE_PRICE_ID=price_...  # Your subscription price ID

# Stripe Webhook Secret (Get after setting up webhook)
STRIPE_WEBHOOK_SECRET=whsec_...  # Will configure this later
```

---

## Step 1: Get Your Stripe Keys

### From Stripe Dashboard:

1. Go to https://dashboard.stripe.com/test
2. Click **Developers** > **API keys**
3. Copy **Secret key** (starts with `sk_test_`)
   - This is your `STRIPE_SECRET_KEY`

---

## Step 2: Get Your Price ID

You already have the product ID: `prod_TEHGknaov9PsfK`

Now get the Price ID:

1. Go to https://dashboard.stripe.com/test/products
2. Click on your product: "AXLY Pro Monthly"
3. Look for the **Price** section
4. Copy the Price ID (starts with `price_`)
   - Example: `price_1AbC123xyz`
   - This is your `STRIPE_PRICE_ID`

**If you don't see a price:**
1. Click "Add another price"
2. Set **Recurring** = Monthly
3. Set **Amount** = $4.99
4. Click "Add price"
5. Copy the new Price ID

---

## Step 3: Set Environment Variables in Azure

### Via Azure Portal:

1. Go to **Azure Portal**
2. Find your Function App: `fa-axlypro-dev`
3. Go to **Configuration**
4. Click **New application setting**
5. Add these 3 settings:

```
Name: STRIPE_SECRET_KEY
Value: sk_test_YOUR_KEY_HERE

Name: STRIPE_PRICE_ID
Value: price_YOUR_PRICE_ID_HERE

Name: STRIPE_WEBHOOK_SECRET
Value: (leave empty for now - will add after webhook setup)
```

6. Click **Save**
7. Click **Continue** to restart the function app

### Via Azure CLI:

```bash
# Set Stripe keys
az functionapp config appsettings set \
  --name fa-axlypro-dev \
  --resource-group axly-dev \
  --settings \
    "STRIPE_SECRET_KEY=sk_test_YOUR_KEY" \
    "STRIPE_PRICE_ID=price_YOUR_PRICE_ID"
```

---

## Step 4: Run Database Migration

### Locally:

```bash
cd diagcar-backend-py

# Install Stripe
pip install -r requirements.txt

# Run migration
alembic upgrade head
```

### On Azure:

The migration will run automatically on next deployment, or run manually:

```bash
# Connect to Azure and run migration
az functionapp deployment source config-zip \
  -g axly-dev \
  -n fa-axlypro-dev \
  --src <path-to-zip>
```

---

## Step 5: Deploy Backend

```bash
cd diagcar-backend-py

# Commit changes
git add .
git commit -m "Add Stripe integration"
git push origin dev

# Azure will auto-deploy from GitHub
# OR manually deploy via Azure Portal
```

---

## Step 6: Setup Stripe Webhook (After Deployment)

Once your backend is deployed:

### 1. Get Your Webhook URL:
```
https://fa-axlypro-dev.azurewebsites.net/webhooks/stripe
```

### 2. Configure in Stripe:

1. Go to **Stripe Dashboard** > **Developers** > **Webhooks**
2. Click **Add endpoint**
3. Enter URL: `https://fa-axlypro-dev.azurewebsites.net/webhooks/stripe`
4. Select events to listen for:
   - ✅ `checkout.session.completed`
   - ✅ `customer.subscription.updated`
   - ✅ `customer.subscription.deleted`
   - ✅ `invoice.payment_succeeded`
   - ✅ `invoice.payment_failed`
5. Click **Add endpoint**
6. Copy the **Signing secret** (starts with `whsec_`)
7. Add to Azure as `STRIPE_WEBHOOK_SECRET`

---

## Step 7: Test the Integration

### Test Checkout Flow:

```bash
# Get a test JWT token first by logging in
TOKEN="your_jwt_token_here"

# Create checkout session
curl -X POST https://fa-axlypro-dev.azurewebsites.net/stripe/create-checkout \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "success_url": "https://axly.pro/success",
    "cancel_url": "https://axly.pro/pricing"
  }'

# Response will include checkout_url - visit in browser
```

### Test with Stripe Test Cards:

Use these test card numbers:
- **Success**: `4242 4242 4242 4242`
- **Decline**: `4000 0000 0000 0002`
- **Requires Auth**: `4000 0025 0000 3155`

Any future expiry date and any 3-digit CVC works.

### Test Webhook:

```bash
# Install Stripe CLI
brew install stripe/stripe-cli/stripe

# Login
stripe login

# Forward webhooks to local
stripe listen --forward-to localhost:7071/webhooks/stripe

# Trigger test event
stripe trigger checkout.session.completed
```

---

## API Endpoints Added

### 1. Create Checkout Session
```
POST /stripe/create-checkout
Authorization: Bearer <token>

{
  "success_url": "https://axly.pro/success",
  "cancel_url": "https://axly.pro/pricing"
}

Response:
{
  "success": true,
  "checkout_url": "https://checkout.stripe.com/...",
  "session_id": "cs_..."
}
```

### 2. Create Customer Portal
```
POST /stripe/create-portal
Authorization: Bearer <token>

{
  "return_url": "https://axly.pro/account"
}

Response:
{
  "success": true,
  "portal_url": "https://billing.stripe.com/..."
}
```

### 3. Stripe Webhook
```
POST /webhooks/stripe
Stripe-Signature: <stripe_signature>

Handles these events:
- checkout.session.completed
- customer.subscription.updated
- customer.subscription.deleted
- invoice.payment_succeeded
- invoice.payment_failed
```

### 4. Subscription Status (Updated)
```
GET /subscriptions/status
Authorization: Bearer <token>

Response (Stripe):
{
  "has_active_subscription": true,
  "status": "active",
  "expires_date": "2025-02-13T12:00:00",
  "product_id": "stripe_monthly",
  "platform": "stripe",
  "auto_renew_status": true
}
```

---

## Database Schema

New table: `stripe_subscriptions`

```sql
CREATE TABLE stripe_subscriptions (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    stripe_customer_id VARCHAR NOT NULL,
    stripe_subscription_id VARCHAR UNIQUE NOT NULL,
    status VARCHAR NOT NULL,
    current_period_end TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

Subscription statuses:
- `active` - Subscription is active
- `past_due` - Payment failed, in grace period
- `canceled` - Subscription canceled
- `incomplete` - Initial payment failed
- `incomplete_expired` - Initial payment expired
- `trialing` - In trial period (if you add trials later)
- `unpaid` - Payment completely failed

---

## Testing Checklist

- [ ] Environment variables set in Azure
- [ ] Database migration ran successfully
- [ ] Backend deployed and running
- [ ] Can create checkout session (returns URL)
- [ ] Can complete checkout with test card
- [ ] Webhook fires on checkout completion
- [ ] User upgraded to PREMIUM tier
- [ ] Subscription status API returns Stripe data
- [ ] Can access customer portal
- [ ] Subscription cancellation works

---

## Troubleshooting

### "STRIPE_SECRET_KEY not set"
- Check Azure Function App Configuration
- Restart function app after adding env vars

### "Price not found"
- Verify `STRIPE_PRICE_ID` is correct
- Make sure it's the Price ID, not Product ID
- Check you're using test mode keys with test prices

### Webhook signature verification failed
- Make sure `STRIPE_WEBHOOK_SECRET` is set
- Verify webhook endpoint URL is correct
- Check Stripe webhook logs for errors

### Migration fails
- Make sure database connection string is correct
- Check if table already exists
- Look at Azure Function logs for SQL errors

---

## Production Checklist

Before going live:

1. **Switch to Live Mode in Stripe**
   - Get live API keys (start with `sk_live_`)
   - Create live product and price
   - Update environment variables with live keys

2. **Update Webhook**
   - Create new webhook for production URL
   - Use live webhook secret

3. **Test in Production**
   - Test with real card (will charge!)
   - Verify webhook fires
   - Test subscription status
   - Test cancellation

4. **Pricing**
   - You're using $4.99/month (test mode)
   - Decide final pricing for production
   - Create price in live mode

---

## Current Configuration

**Test Mode:**
- Product ID: `prod_TEHGknaov9PsfK`
- Price: $4.99/month
- Price ID: (get from Stripe dashboard)

**Backend:**
- Function App: `fa-axlypro-dev`
- Webhook URL: `https://fa-axlypro-dev.azurewebsites.net/webhooks/stripe`

**Next Steps:**
1. Get Price ID from Stripe
2. Set environment variables in Azure
3. Deploy backend
4. Setup webhook
5. Test complete flow

---

Ready to continue? Get your Price ID from Stripe and we'll configure it!
