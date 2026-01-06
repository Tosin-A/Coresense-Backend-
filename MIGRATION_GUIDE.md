# CoreSense Backend Migration Guide

## Overview

This guide helps migrate from the old overlapping coaching services to the new unified architecture.

## Migration Steps

### Phase 1: Foundation (Completed ✅)

- [x] Created unified coaching service (`coaching_service.py`)
- [x] Extracted thread management service (`thread_management.py`)
- [x] Extracted context service (`context_service.py`)
- [x] Created unified coaching router (`coaching_router.py`)

### Phase 2: Migration (Current Phase)

#### Step 1: Update Imports

**Old imports to replace:**

```python
# In routers/openai_coach.py
from backend.services.openai_coach_service import openai_coach_service
from backend.services.custom_gpt_service import custom_gpt_service

# In routers/ai_coach.py
from backend.services.ai_coach import get_model_info, is_model_available
```

**New imports:**

```python
# Replace with unified service
from backend.services.coaching_service import unified_coaching_service
from backend.services.thread_management import thread_management
from backend.services.context_service import context_service
```

#### Step 2: Update Endpoint Implementations

**Old pattern:**

```python
@router.post("/chat")
async def chat_with_coach(request: Request, user_id: str = Depends(get_user)):
    # Multiple service calls
    context = await context_injector.get_comprehensive_context(user_id)
    response = await custom_gpt_service.chat_with_coach(user_id, message)
    # More complex logic
```

**New pattern:**

```python
@router.post("/chat")
async def chat_with_coach(request: CoachingChatRequest, user_id: str = Depends(get_user)):
    # Single unified call
    response = await unified_coaching_service.chat(
        user_id=user_id,
        message=request.message,
        response_type=request.response_type,
        context=request.context
    )
    return response
```

#### Step 3: Update Router Registration

**In main.py:**

```python
# Remove old imports
# from backend.routers.ai_coach import router as ai_coach_router
# from backend.routers.openai_coach import router as openai_coach_router

# Add new import
from backend.routers.coaching_router import router as coaching_router

# Update router registration
app.include_router(coaching_router)  # Replace the old ones
```

### Phase 3: Remove Redundant Services

#### Services to Remove:

1. **`routers/ai_coach.py`** - All functionality moved to `coaching_router.py`
2. **`services/custom_gpt_service.py`** - Logic integrated into `coaching_service.py`
3. **`services/openai_coach_service.py`** - Create missing file or integrate logic

#### Services to Simplify:

1. **`services/thread_management.py`** - Core thread management service
2. **`services/context_injector.py`** - Keep as wrapper, core logic in `context_service.py`

## API Endpoint Migration

### Old Endpoints → New Endpoints

| Old Endpoint                               | New Endpoint                           | Notes                           |
| ------------------------------------------ | -------------------------------------- | ------------------------------- |
| `POST /api/ai-coach/personalized-chat`     | `POST /api/v1/coach/chat`              | Use `response_type: "coaching"` |
| `POST /api/ai-coach/user-context`          | `GET /api/v1/coach/context/{user_id}`  | GET instead of POST             |
| `POST /api/ai-coach/personalized-advice`   | `POST /api/v1/coach/chat`              | Use `response_type: "advice"`   |
| `POST /api/ai-coach/health-insights`       | `GET /api/v1/coach/insights/{user_id}` | GET instead of POST             |
| `POST /api/ai-coach/coaching-stats`        | `GET /api/v1/coach/stats/{user_id}`    | GET instead of POST             |
| `GET /api/ai-coach/coach-status/{user_id}` | `GET /api/v1/coach/status/{user_id}`   | Same endpoint, unified logic    |
| `POST /api/v1/coach/chat`                  | `POST /api/v1/coach/chat`              | Enhanced with unified service   |
| `POST /api/v1/coach/greeting`              | `POST /api/v1/coach/chat`              | Use `response_type: "greeting"` |
| `POST /api/v1/coach/pressure`              | `POST /api/v1/coach/chat`              | Use `response_type: "pressure"` |

### Request Body Changes

**Old ai_coach.py format:**

```json
{
  "message": "string",
  "context": {
    "user_state": {},
    "conversation_context": [],
    "health_context": {},
    "time_context": {}
  },
  "response_type": "personal_coaching"
}
```

**New unified format:**

```json
{
  "message": "string",
  "context": {
    "user_state": {},
    "conversation_context": [],
    "health_context": {},
    "time_context": {}
  },
  "response_type": "coaching" // Use CoachingResponseType enum values
}
```

## Backward Compatibility

### Maintained Compatibility

The new `coaching_router.py` includes backward compatibility endpoints:

- `POST /api/v1/coach/greeting` - Maps to unified chat with `response_type: "greeting"`
- `POST /api/v1/coach/pressure` - Maps to unified chat with `response_type: "pressure"`
- `GET /api/v1/coach/stats/{user_id}` - Maps to insights endpoint

### Deprecation Timeline

1. **Week 1-2**: New endpoints available alongside old ones
2. **Week 3**: Old endpoints marked as deprecated
3. **Week 4**: Old endpoints removed

## Testing Strategy

### Unit Tests

```python
# Test unified coaching service
def test_unified_coaching_chat():
    response = await unified_coaching_service.chat(
        user_id="test_user",
        message="Hello",
        response_type=CoachingResponseType.COACHING
    )
    assert response.messages
    assert response.personality_score > 0

# Test thread management
def test_thread_management():
    thread_id = await thread_management.get_or_create_user_thread("test_user")
    assert thread_id
```

### Integration Tests

```python
# Test unified router
def test_coaching_router_chat():
    response = client.post("/api/v1/coach/chat", json={
        "message": "Hello",
        "response_type": "coaching"
    })
    assert response.status_code == 200
    assert "messages" in response.json()
```

### Performance Tests

- Measure response time improvements
- Verify reduced database queries
- Confirm memory usage reduction

## Rollback Plan

### If Issues Arise

1. **Immediate rollback**: Revert `main.py` to use old routers
2. **Database rollback**: No schema changes required
3. **Service rollback**: Old services remain functional

### Rollback Commands

```bash
# Revert main.py changes
git checkout HEAD~1 -- backend/main.py

# Restart server
./start.sh
```

## Success Criteria

### Code Quality Metrics

- [ ] 40-50% reduction in coaching-related code
- [ ] 80%+ test coverage maintained
- [ ] Cyclomatic complexity reduced by 30%

### Performance Metrics

- [ ] Response time maintained or improved
- [ ] Memory usage reduced by 20%
- [ ] Database queries reduced by 40%

### Developer Experience Metrics

- [ ] Time to implement new coaching features reduced by 50%
- [ ] Bug resolution time reduced by 40%
- [ ] Code review time reduced by 30%

## Support and Troubleshooting

### Common Issues

1. **Import errors**: Ensure all new services are properly imported
2. **Missing endpoints**: Check router registration in main.py
3. **Database errors**: Verify thread and context tables exist

### Debug Commands

```bash
# Check service status
curl http://localhost:8000/api/v1/coach/status

# Test unified chat
curl -X POST http://localhost:8000/api/v1/coach/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello", "response_type": "greeting"}'
```

### Monitoring

- Monitor error rates during migration
- Track performance metrics
- Watch for memory leaks
- Verify message limit functionality

## Next Steps

After migration completion:

1. Remove deprecated endpoints
2. Clean up old service files
3. Update documentation
4. Train team on new architecture
5. Optimize based on usage patterns
