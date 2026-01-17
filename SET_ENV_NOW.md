# ⚠️ URGENT: Set Environment Variables in Railway

## Current Status
✅ Build successful
✅ PORT variable working (8080)
❌ **MISSING**: `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` environment variables

## Quick Fix - Set Variables Now

### Option 1: Railway Dashboard (Easiest)

1. Go to https://railway.app
2. Select your project
3. Click on your service (backend)
4. Go to **"Variables"** tab
5. Click **"+ New Variable"** and add:

```
Name: SUPABASE_URL
Value: https://ngcmutnfqelsqiuitcfw.supabase.co
```

```
Name: SUPABASE_SERVICE_KEY
Value: [Get from Supabase Dashboard → Settings → API → service_role key]
```

```
Name: OPENAI_API_KEY
Value: [Your OpenAI API key]
```

```
Name: GPT_MODEL
Value: gpt-4o-mini
```

```
Name: ENVIRONMENT
Value: production
```

### Option 2: Railway CLI (Quick)

Run these commands from the `backend` directory:

```bash
cd backend

railway variables set SUPABASE_URL=https://ngcmutnfqelsqiuitcfw.supabase.co
railway variables set SUPABASE_SERVICE_KEY=your_service_role_key_here
railway variables set OPENAI_API_KEY=your_openai_key_here
railway variables set GPT_MODEL=gpt-4o-mini
railway variables set ENVIRONMENT=production

# Verify they're set
railway variables
```

## 🔑 How to Get Your Supabase Service Key

1. Go to https://app.supabase.com
2. Select your project: `ngcmutnfqelsqiuitcfw`
3. Click **Settings** (gear icon) → **API**
4. Scroll to **"Project API keys"** section
5. Copy the **`service_role`** key (the secret one, NOT the anon/public key!)
   - It should start with `eyJhbGci...`
   - When decoded, it contains `"role":"service_role"`

## ⚠️ IMPORTANT

- Use the **service_role** key, NOT the anon key
- The service_role key has full database access
- Never expose this key in client-side code
- It's safe to use in Railway's backend environment variables

## After Setting Variables

Railway will automatically redeploy. Check logs:

```bash
railway logs
```

You should see the server start successfully without the validation errors!
