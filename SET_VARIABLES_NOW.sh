#!/bin/bash
# Script to set all required Railway environment variables
# Usage: ./SET_VARIABLES_NOW.sh

echo "🔧 Setting Railway Environment Variables..."
echo ""

cd "$(dirname "$0")"

# Check if railway CLI is available
if ! command -v railway &> /dev/null; then
    echo "❌ Railway CLI not found. Install with: npm install -g @railway/cli"
    exit 1
fi

# Set variables that don't require secrets
echo "Setting basic variables..."
railway variables --set "SUPABASE_URL=https://ngcmutnfqelsqiuitcfw.supabase.co"
railway variables --set "GPT_MODEL=gpt-4o-mini"
railway variables --set "ENVIRONMENT=production"

echo ""
echo "✅ Basic variables set!"
echo ""
echo "⚠️  IMPORTANT: You MUST manually set these secret variables:"
echo ""
echo "   1. SUPABASE_SERVICE_KEY (service_role key from Supabase)"
echo "   2. OPENAI_API_KEY (your OpenAI API key)"
echo ""
echo "To set them, run:"
echo ""
echo "   railway variables --set \"SUPABASE_SERVICE_KEY=your_service_role_key_here\""
echo "   railway variables --set \"OPENAI_API_KEY=your_openai_key_here\""
echo ""
echo "📋 Current variables:"
railway variables

echo ""
echo "🔑 How to get SUPABASE_SERVICE_KEY:"
echo "   1. Go to https://app.supabase.com"
echo "   2. Select project: ngcmutnfqelsqiuitcfw"
echo "   3. Settings → API"
echo "   4. Copy the 'service_role' key (NOT anon key!)"
echo ""
echo "After setting SUPABASE_SERVICE_KEY and OPENAI_API_KEY, Railway will automatically redeploy."
