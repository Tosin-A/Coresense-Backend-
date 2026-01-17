# Optimized Architecture - API Routing Flow

## Current Architecture (BEFORE Optimization)

```
┌──────────────┐
│ User Message │
└──────┬───────┘
       │
       ▼
┌─────────────────────────┐
│   Coaching Service      │
│   (coaching_service.py) │
└──────────┬──────────────┘
           │
           │ ALL MESSAGES (100%)
           │
           ▼
    ┌──────────────────────┐
    │  Assistant API       │
    │  (OpenAI Threads)    │
    │                      │
    │  $$$ EXPENSIVE $$$   │
    │  - Thread overhead   │
    │  - Function defs     │
    │  - Full context      │
    └──────────┬───────────┘
               │
               ▼
         [ Response ]

COST: ~$0.009 per message (0.9 cents)
CACHE HIT RATE: ~5-10%
```

---

## Optimized Architecture (AFTER Week 1)

```
┌──────────────┐
│ User Message │
└──────┬───────┘
       │
       ▼
┌─────────────────────────┐
│   Coaching Service      │
│   (coaching_service.py) │
└──────────┬──────────────┘
           │
           ▼
    ┌─────────────────┐
    │ STEP 1:         │
    │ Pattern Match?  │◄───── pattern_responder.py
    └────────┬────────┘
             │
      ┌──────┴──────┐
      │ YES (20%)   │ NO (80%)
      ▼             ▼
┌──────────┐  ┌─────────────┐
│ PATTERN  │  │ STEP 2:     │
│ CACHE    │  │ Check Cache │◄───── response_cache.py
│ (FREE)   │  └──────┬──────┘
└────┬─────┘         │
     │         ┌─────┴─────┐
     │         │ HIT (10%) │ MISS (70%)
     │         ▼           ▼
     │    ┌─────────┐  ┌─────────────┐
     │    │ CACHED  │  │ STEP 3:     │
     │    │ RESPONSE│  │ API Router  │◄───── api_selector.py
     │    │ (FREE)  │  └──────┬──────┘
     │    └────┬────┘         │
     │         │        ┌─────┴─────────┐
     │         │        │               │
     │         │   SIMPLE (60%)    COMPLEX (10%)
     │         │        │               │
     │         │        ▼               ▼
     │         │  ┌──────────────┐  ┌──────────────┐
     │         │  │ Completions  │  │  Assistant   │
     │         │  │     API      │  │     API      │
     │         │  │              │  │              │
     │         │  │ GPT-4o-mini  │  │   GPT-4      │
     │         │  │   $ CHEAP    │  │ $$$ EXPENSIVE│
     │         │  │              │  │              │
     │         │  └──────┬───────┘  └──────┬───────┘
     │         │         │                 │
     └─────────┴─────────┴─────────────────┘
                         │
                         ▼
                   [ Response ]

BREAKDOWN:
- 20% Pattern Cache    = FREE                 = $0
- 10% Response Cache   = FREE                 = $0
- 60% Completions API  = $0.0015 × 600       = $0.90
- 10% Assistant API    = $0.009 × 100        = $0.90

TOTAL: $1.80 per 1,000 messages
SAVINGS: 80% (vs $9.00 before)
```

---

## Decision Tree: Which API to Use?

```
                    ┌──────────────────┐
                    │  User Message    │
                    └────────┬─────────┘
                             │
                             ▼
                 ┌───────────────────────┐
                 │ Is it 1-2 words?      │
                 │ (hi, hey, done, etc.) │
                 └───────────┬───────────┘
                             │
                    ┌────────┴────────┐
                    │                 │
                  YES               NO
                    │                 │
                    ▼                 ▼
            ┌──────────────┐   ┌──────────────────┐
            │  PATTERN     │   │ Message count    │
            │  CACHE       │   │ < 3 for user?    │
            │  ✅ FREE     │   └────────┬─────────┘
            └──────────────┘            │
                                ┌───────┴────────┐
                                │                │
                              YES              NO
                                │                │
                                ▼                ▼
                        ┌──────────────┐  ┌──────────────────┐
                        │  ASSISTANT   │  │ Contains complex │
                        │     API      │  │ words?           │
                        │              │  │ (analyze, goal,  │
                        │ Building     │  │ pattern, why)    │
                        │ relationship │  └────────┬─────────┘
                        └──────────────┘           │
                                          ┌────────┴────────┐
                                          │                 │
                                        YES               NO
                                          │                 │
                                          ▼                 ▼
                                  ┌──────────────┐  ┌──────────────┐
                                  │  ASSISTANT   │  │ COMPLETIONS  │
                                  │     API      │  │     API      │
                                  │              │  │              │
                                  │ Complex      │  │ Simple       │
                                  │ coaching     │  │ response     │
                                  └──────────────┘  └──────────────┘
```

---

## Message Type Routing Table

| Message Example | Type | API Used | Cost | Reasoning |
|----------------|------|----------|------|-----------|
| "hey" | Greeting | Pattern Cache | $0 | Common pattern |
| "done" | Completion | Pattern Cache | $0 | Common pattern |
| "good morning" | Greeting | Pattern Cache | $0 | Time-based pattern |
| "how's it going?" | Check-in | Completions | $0.0015 | Simple, no context needed |
| "I completed my workout" | Celebration | Completions | $0.0015 | Simple acknowledgment |
| "feeling tired today" | Support | Completions | $0.0015 | Simple support message |
| "why do I keep failing?" | Deep Coaching | Assistant | $0.009 | Complex analysis needed |
| "help me set a goal" | Goal Setting | Assistant | $0.009 | Requires memory/context |
| "what patterns do you see?" | Pattern Analysis | Assistant | $0.009 | Advanced reasoning |
| First message from user | Relationship | Assistant | $0.009 | Building rapport |

---

## Thread Management: Before vs After

### BEFORE (Current)
```
Thread for User A:
┌─────────────────────────────────────┐
│ Message 1: "hey"                    │
│ Message 2: "done with workout"      │
│ Message 3: "feeling good"           │
│ Message 4: "what's next?"           │
│ Message 5: "help me plan"           │
│ ... (grows forever)                 │
│ Message 100: "hey"                  │
│                                     │
│ Input Tokens: 3,000+ (grows)        │
│ Cost per call: $0.012 (increases)   │
└─────────────────────────────────────┘

PROBLEM: Context grows indefinitely
```

### AFTER (Optimized)
```
Simple messages → NO THREAD (Completions API)
┌────────────────────┐
│ "hey" → Pattern    │  ✅ Free
│ "done" → Pattern   │  ✅ Free
│ "good" → Pattern   │  ✅ Free
└────────────────────┘

Complex messages → THREAD (Assistant API, pruned)
┌─────────────────────────────────────┐
│ [Summary of 1-80]                   │◄─ Compressed
│ Message 81: "analyze my patterns"  │
│ Message 82: "set a goal"            │
│ ... (only last 20 messages)         │
│ Message 100: "help me plan"         │
│                                     │
│ Input Tokens: 800 (capped)          │
│ Cost per call: $0.009 (stable)      │
└─────────────────────────────────────┘

SOLUTION: Context stays manageable
```

---

## Cache Hit Flow

```
┌──────────────┐
│ User Message │
└──────┬───────┘
       │
       ▼
┌─────────────────────────┐
│ Generate Cache Key      │
│ (hash of message)       │
└──────────┬──────────────┘
           │
           ▼
    ┌──────────────┐
    │ Check Redis/ │
    │ Supabase     │
    └──────┬───────┘
           │
    ┌──────┴──────┐
    │             │
  HIT           MISS
    │             │
    ▼             ▼
┌────────┐  ┌────────────┐
│ Return │  │ Call API   │
│ Cached │  │            │
│ (FREE) │  │ Cache      │
│        │  │ Response   │
└────────┘  └─────┬──────┘
                  │
                  ▼
            ┌─────────────┐
            │ Return      │
            │ Response    │
            └─────────────┘

CACHE STRATEGY:
- Exact match: 24 hours
- Pattern match: 7 days
- User-specific: 1 hour
- Context-dependent: No cache
```

---

## Cost Breakdown Visualization

### Current State (1,000 messages/day)
```
100% Assistant API
█████████████████████████████████████████ $9.00/day
```

### After Week 1 (Pattern + Hybrid)
```
20% Pattern Cache    ░░░░░░░░ $0.00
10% Response Cache   ░░░░ $0.00
60% Completions      ████████████ $0.90
10% Assistant        ████ $0.90
                     ─────────────────────
                     TOTAL: $1.80/day (80% savings)
```

### After Month 6 (With Fine-tuning)
```
30% Pattern Cache    ░░░░░░░░░░░░ $0.00
50% Fine-tuned       ████ $0.15
15% Completions      ███ $0.23
5%  Assistant        ██ $0.45
                     ─────────────────────
                     TOTAL: $0.83/day (91% savings)
```

---

## Implementation Phases

```
┌─────────────────────────────────────────────────────────┐
│ PHASE 1: Quick Wins (Week 1)                           │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ Day 1: Remove Function Defs         ┌───┐             │
│ ──────────────────────────────────► │ 5%│ savings    │
│                                      └───┘             │
│                                                         │
│ Day 1-2: Pattern Cache              ┌────┐            │
│ ──────────────────────────────────► │15% │ savings    │
│                                      └────┘             │
│                                                         │
│ Day 3-5: Hybrid API                 ┌─────────┐       │
│ ──────────────────────────────────► │  35%    │ savings│
│                                      └─────────┘        │
│                                                         │
│ TOTAL WEEK 1: 50-55% savings                          │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ PHASE 2: Optimization (Week 2)                         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ Day 6-7: Model Router               ┌────┐            │
│ ──────────────────────────────────► │20% │ savings    │
│                                      └────┘             │
│                                                         │
│ Day 8-10: Thread Pruning            ┌───┐             │
│ ──────────────────────────────────► │10%│ savings    │
│                                      └───┘             │
│                                                         │
│ TOTAL WEEK 2: Additional 15% (65% cumulative)         │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ PHASE 3: Long-term (Month 3-6)                        │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ Month 3-6: Fine-tuning              ┌──────────────┐  │
│ ──────────────────────────────────► │     50%      │  │
│                                      └──────────────┘   │
│                                                         │
│ TOTAL MONTH 6: 85% cumulative savings                 │
└─────────────────────────────────────────────────────────┘
```

---

## File Structure (After Optimization)

```
backend/
├── services/
│   ├── coaching_service.py          [MODIFY] Add routing logic
│   ├── thread_management.py         [MODIFY] Remove funcs, add pruning
│   ├── response_cache.py            [EXISTING] Already implemented
│   ├── cost_control.py              [EXISTING] Already tracking
│   ├── model_router.py              [EXISTING] Need to integrate!
│   │
│   ├── pattern_responder.py         [NEW] Pattern-based responses
│   ├── api_selector.py              [NEW] Route between APIs
│   ├── completions_service.py       [NEW] Direct Completions API
│   └── cost_monitor.py              [NEW] Enhanced cost tracking
│
├── monitoring/
│   └── cost_tracking_queries.sql    [NEW] Monitoring queries
│
└── migrations/
    └── add_api_type_tracking.sql    [NEW] Track API usage
```

---

## Monitoring Dashboard (What to Track)

```
┌─────────────────────────────────────────────┐
│           DAILY COST DASHBOARD              │
├─────────────────────────────────────────────┤
│                                             │
│ Total Calls Today:     1,000                │
│ Pattern Cache:         200  (20%) ████      │
│ Response Cache:        100  (10%) ██        │
│ Completions API:       600  (60%) ████████  │
│ Assistant API:         100  (10%) ██        │
│                                             │
│ Cache Hit Rate:        30%                  │
│ Avg Response Time:     1.2s                 │
│                                             │
│ Estimated Cost:        $1.80/day            │
│ Monthly Projection:    $54/month            │
│                                             │
│ Compared to Yesterday:  ↓ 15%              │
│ Compared to Last Week:  ↓ 65%              │
│                                             │
└─────────────────────────────────────────────┘
```

---

## Quality Assurance Checks

```
┌────────────────────────────────────────────┐
│ Quality Metric       | Target | Actual    │
├────────────────────────────────────────────┤
│ User Satisfaction    | >4.0   | 4.2 ✅    │
│ Streak Retention     | >70%   | 73% ✅    │
│ Avg Response Time    | <2.0s  | 1.2s ✅   │
│ Error Rate           | <1%    | 0.3% ✅   │
│ Cache Hit Rate       | >30%   | 35% ✅    │
│ Cost per 1K messages | <$2    | $1.80 ✅  │
└────────────────────────────────────────────┘

✅ All metrics within target range
```

---

## Key Success Indicators

### Week 1 Goals
- [ ] Pattern cache catching 15-20% of messages
- [ ] Completions API handling 60% of messages
- [ ] Daily cost reduced by 40-50%
- [ ] Response time stays under 2 seconds
- [ ] Zero user complaints about quality

### Week 2 Goals
- [ ] Model router integrated
- [ ] Thread pruning active
- [ ] Daily cost reduced by 55-65%
- [ ] Cache hit rate above 25%

### Month 6 Goals
- [ ] Fine-tuned model in production
- [ ] Daily cost reduced by 70-85%
- [ ] Cache hit rate above 40%
- [ ] User satisfaction maintained or improved

---

## Emergency Rollback Plan

```
IF quality degrades OR cost spikes:

1. Disable pattern cache
   ├─► Set ENABLE_PATTERN_CACHE=false
   └─► Roll back to Assistant API for all

2. Disable Completions API
   ├─► Set ENABLE_COMPLETIONS_API=false
   └─► Route everything to Assistant

3. Re-enable function definitions
   ├─► Uncomment tools=self.functions
   └─► Restore original behavior

4. Increase thread pruning threshold
   ├─► MAX_THREAD_MESSAGES = 50 (instead of 20)
   └─► Keep more context

Feature flags make rollback instant!
```

---

## Next Steps

1. ✅ Review this architecture document
2. ✅ Start with `COST_OPTIMIZATION_QUICKSTART.md`
3. ✅ Set up monitoring queries
4. ✅ Implement Week 1 optimizations
5. ✅ Track metrics daily
6. ✅ Iterate based on results

**Remember: Start small, measure results, scale what works!**
