# ⚠️ URGENT: Set Missing Environment Variable

## Current Status
✅ Build: Successful  
✅ PORT: Working (8080)  
✅ SUPABASE_URL: Set  
❌ **MISSING**: `SUPABASE_SERVICE_KEY`  
❌ **MISSING**: `OPENAI_API_KEY` (optional but needed for AI features)

## Quick Fix - Set SUPABASE_SERVICE_KEY Now

### Option 1: Railway Dashboard (Easiest)

1. Go to https://railway.app
2. Select your project → Your service
3. Click **"Variables"** tab
4. Click **"+ New Variable"**
5. Add:
   - **Name**: `SUPABASE_SERVICE_KEY`
   - **Value**: [Get from Supabase Dashboard - see instructions below]

### Option 2: Railway CLI (Quick)

```bash
cd backend

# Set Supabase Service Key
railway variables --set "SUPABASE_SERVICE_KEY=your_service_role_key_here"

# Set OpenAI API Key (if you have one)
railway variables --set "OPENAI_API_KEY=your_openai_key_here"
```

### Option 3: Both at Once

```bash
cd backend

railway variables --set "SUPABASE_SERVICE_KEY=your_key" --set "OPENAI_API_KEY=your_key"
```

---

## 🔑 How to Get Your Supabase Service Key

1. **Go to Supabase Dashboard**: https://app.supabase.com
2. **Select your project**: `ngcmutnfqelsqiuitcfw`
3. **Click Settings** (gear icon in left sidebar)
4. **Click "API"** in the settings menu
5. **Scroll down to "Project API keys"** section
6. **Find "service_role" key** (it's the secret one, usually shown with a "Reveal" button)
7. **Click "Reveal"** and copy the entire key
   - It should start with `eyJhbGci...`
   - It's very long (several hundred characters)
8. **Paste it into Railway**

**⚠️ IMPORTANT**: 
- Use the **service_role** key (NOT the anon/public key)
- The service_role key has full database access
- It's safe to use in Railway backend environment variables
- Never expose it in client-side code

---

## Verify Variables Are Set

After setting, check:

```bash
railway variables
```

You should see:
- ✅ `SUPABASE_URL`
- ✅ `SUPABASE_SERVICE_KEY` (NEW!)
- ✅ `GPT_MODEL`
- ✅ `ENVIRONMENT`
- ✅ `OPENAI_API_KEY` (if you set it)

---

## After Setting Variables

Railway will **automatically redeploy** when you save variables. Check logs:

```bash
railway logs
```

The server should start successfully without validation errors!

---

## If You Don't Have OPENAI_API_KEY Yet

The app will start without it, but AI coaching features won't work. You can:
1. Set it later when you get an OpenAI API key
2. Or make it optional in the config (we can do this if needed)
