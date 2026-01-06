# CoreSense Backend

Backend API server for CoreSense personal AI coach. This server orchestrates Messages integration, user state management, and synchronization between the app and Messages interface.

## Architecture

- **FastAPI** - Python web framework
- **Supabase** - Database and authentication
- **Pydantic** - Data validation and type hints
- **Python-JOSE** - JWT token verification

## Setup

### 1. Create Virtual Environment and Install Dependencies

```bash
cd backend
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**Note**: Always activate the virtual environment before running the server:
```bash
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Configure Environment

Create a `.env` file in the `backend/` directory:

```bash
cd backend
# Create .env file (see below for contents)
```

**Required environment variables**:
- `SUPABASE_URL` - Your Supabase project URL (e.g., `https://ngcmutnfqelsqiuitcfw.supabase.co`)
- `SUPABASE_SERVICE_KEY` - Service role key (not anon key - get this from Supabase Dashboard → Settings → API → service_role key)

**Example `.env` file**:
```env
SUPABASE_URL=https://ngcmutnfqelsqiuitcfw.supabase.co
SUPABASE_SERVICE_KEY=your_service_role_key_here
PORT=8000
ENVIRONMENT=development
```

**Note**: This is separate from `coresense/.env` (which is for the React Native app). The backend needs its own `.env` file with the service role key.

### 3. Run Database Migration

Run the SQL script in Supabase SQL Editor:
```bash
# File: coresense/MILESTONE_1_DATABASE_SCHEMA.sql
```

This creates the required tables:
- `conversation_memory` - Message history
- `coach_state` - User engagement tracking
- `user_phone_numbers` - Phone number mapping

### 4. Start Server

```bash
python main.py
```

Or with uvicorn directly:
```bash
uvicorn main:app --reload --port 8000
```

Server will start on `http://localhost:8000`

## API Endpoints

### Health Check

```
GET /health
```

Returns server health status.

### Phone Number Management

#### Register Phone Number
```
POST /api/users/{user_id}/phone
Authorization: Bearer <supabase_jwt_token>
Content-Type: application/json

{
  "phone_number": "+44741749998",
  "is_verified": false
}
```

#### Get Phone Numbers
```
GET /api/users/{user_id}/phone
Authorization: Bearer <supabase_jwt_token>
```

### Coach State

#### Get Coach State
```
GET /api/users/{user_id}/coach-state
Authorization: Bearer <supabase_jwt_token>
```

Returns coach state (creates default if doesn't exist).

### Conversation Memory

#### Get Conversation History
```
GET /api/users/{user_id}/conversation-memory?limit=50
Authorization: Bearer <supabase_jwt_token>
```

Returns recent messages in chronological order.

## Authentication

All API endpoints (except `/health` and `/`) require authentication via Supabase JWT token:

```
Authorization: Bearer <jwt_token>
```

The token should be obtained from the app after user signs in via Supabase Auth.

## Testing

### Using curl

```bash
# Get JWT token from app (Supabase Auth)
TOKEN="your_jwt_token_here"
USER_ID="user_uuid_here"

# Register phone number
curl -X POST "http://localhost:8000/api/users/$USER_ID/phone" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "+44741749998", "is_verified": false}'

# Get phone numbers
curl "http://localhost:8000/api/users/$USER_ID/phone" \
  -H "Authorization: Bearer $TOKEN"

# Get coach state
curl "http://localhost:8000/api/users/$USER_ID/coach-state" \
  -H "Authorization: Bearer $TOKEN"

# Get conversation memory
curl "http://localhost:8000/api/users/$USER_ID/conversation-memory?limit=10" \
  -H "Authorization: Bearer $TOKEN"
```

### Using FastAPI Docs

Navigate to `http://localhost:8000/docs` for interactive API documentation.

## Project Structure

```
backend/
├── main.py                  # FastAPI app entry point
├── config.py                # Configuration management
├── database/
│   ├── supabase_client.py  # Supabase client and helpers
│   └── models.py           # Pydantic data models
└── routers/
    └── app_api.py          # API endpoints
```

## Development

- Server auto-reloads on code changes (when using `--reload`)
- Check logs in terminal for debugging
- Use FastAPI docs at `/docs` for testing

## Next Steps

This is Milestone 1 - foundation only. Future milestones will add:
- GPT wrapper for message generation
- Message orchestration engine
- Twilio SMS/iMessage integration
- Memory service logic

