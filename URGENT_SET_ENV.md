# ⚠️ URGENT: Set SUPABASE_SERVICE_KEY to Fix Deployment

## Error Message
```
supabase_service_key: Field required [type=missing]
```

## ✅ What's Working
- ✅ Build: Successful
- ✅ PORT: Working (8080) 
- ✅ SUPABASE_URL: Set
- ✅ GPT_MODEL: Set
- ✅ ENVIRONMENT: Set

## ❌ What's Missing
- ❌ **SUPABASE_SERVICE_KEY** (REQUIRED - app won't start without this!)
- ⚠️ OPENAI_API_KEY (optional - AI features won't work without it)

---

## 🔧 Quick Fix - Set Variables Now

### Method 1: Railway CLI (Fastest)

```bash
cd backend

# Set the missing Supabase Service Key
railway variables --set "SUPABASE_SERVICE_KEY=your_service_role_key_here"

# Optional: Set OpenAI API Key for AI features
railway variables --set "OPENAI_API_KEY=your_openai_key_here"
```

### Method 2: Railway Dashboard

1. Go to: https://railway.app
2. Select your project → Click on your service
3. Click **"Variables"** tab
4. Click **"+ New Variable"**
5. Add:
   - **Name**: `SUPABASE_SERVICE_KEY`
   - **Value**: [Get from Supabase - see below]

---

## 🔑 Get Your Supabase Service Key

1. **Open Supabase Dashboard**: https://app.supabase.com
2. **Select Project**: `ngcmutnfqelsqiuitcfw`
3. **Settings** (⚙️ gear icon) → **API**
4. **Scroll to "Project API keys"**
5. **Find "service_role"** (the secret key, not anon key)
6. **Click "Reveal"** to show the key
7. **Copy the entire key** (it's very long, starts with `eyJhbGci...`)

**⚠️ CRITICAL**: 
- Must be the **service_role** key (NOT anon/public key)
- It's the one that says "secret" and is usually hidden
- This key has full database access - safe for backend, never use in frontend!

---

## ✅ After Setting

Railway will automatically redeploy. Your app should start successfully!

Check logs:
```bash
railway logs
```

You should see the server start without errors.
