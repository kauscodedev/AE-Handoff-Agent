# AE Handoff Brief Agent — Setup Guide

## Prerequisites

- Python 3.8+
- Access to HubSpot API v3
- Deepgram account with API key
- OpenAI account with API key
- Supabase project with `calls` table (from call-scoring-agent)

## Installation

### 1. Clone / Copy Project
```bash
cd /Users/kaustubhchauhan/ae-handoff-brief-agent
```

### 2. Create Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
```bash
cp .env.example .env
# Edit .env with your API keys:
cat > .env << 'EOF'
HUBSPOT_TOKEN=your-hubspot-token-here
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-key-here
DEEPGRAM_API_KEY=your-deepgram-key-here
OPENAI_API_KEY=your-openai-key-here
EOF
```

### 5. Create Log Directory
```bash
mkdir -p logs
```

## Verification

### Test HubSpot Connection
```bash
python3 -c "
from lib.hubspot_client import get_owner_name
print('✓ HubSpot client loaded')
"
```

### Test Supabase Connection
```bash
python3 -c "
from lib.supabase_client import get_supabase
db = get_supabase()
print('✓ Supabase client connected')
"
```

### Run Single Iteration
```bash
python3 orchestrator.py --once
```

Expected output:
```
[INFO] AE Handoff Brief Agent — Orchestrator Starting
[INFO] Checking for pending calls...
[INFO] No pending calls found
```

## Database Schema Requirements

Ensure your Supabase `calls` table has these columns:

```sql
-- New columns (if not already added by call-scoring-agent migration)
ALTER TABLE calls ADD COLUMN ae_brief_sent BOOLEAN DEFAULT FALSE;
ALTER TABLE calls ADD COLUMN ae_brief_generated_at TIMESTAMP;
```

## Start the Orchestrator

### Option 1: Continuous Loop (Recommended)
```bash
python3 orchestrator.py
```
- Polls HubSpot every 60 seconds
- Processes pending "C - Meeting Scheduled" calls
- Runs forever (Ctrl+C to stop)

### Option 2: Custom Interval
```bash
python3 orchestrator.py --interval 120
```
- Checks every 120 seconds instead of 60

### Option 3: Single Run
```bash
python3 orchestrator.py --once
```
- Runs one iteration only
- Useful for testing or scheduled jobs (cron, GitHub Actions)

## Monitoring

### Watch Logs in Real-Time
```bash
tail -f logs/orchestrator.log
```

### Check Specific Error
```bash
grep "✗" logs/orchestrator.log | tail -10
```

### View Generated Briefs
```bash
ls -la handoffs/
cat handoffs/Garden_State_Honda_handoff.md
```

## Troubleshooting

### Issue: "No meetings found after checking HubSpot"

**Diagnosis:**
1. Check that calls in HubSpot have `hs_call_disposition` set to "C - Meeting Scheduled"
2. Verify calls are being logged from your dialer (Nooks)
3. Ensure the company in HubSpot has `lifecyclestage` = lead or marketingqualifiedlead

**Solution:**
```bash
# Check call count in Supabase
psql $SUPABASE_URL << 'EOF'
SELECT COUNT(*) FROM calls WHERE call_disposition_label = 'C - Meeting Scheduled' AND ae_brief_sent = FALSE;
EOF
```

### Issue: "Deepgram API error"

**Diagnosis:**
- Check DEEPGRAM_API_KEY is correct
- Verify recording_url is publicly accessible
- Ensure Deepgram account has available credits

**Solution:**
```bash
# Test Deepgram connection
python3 -c "
import requests
headers = {'Authorization': f'Token {DEEPGRAM_API_KEY}'}
response = requests.get('https://api.deepgram.com/v1/status', headers=headers)
print(response.status_code)
"
```

### Issue: "OpenAI error: Insufficient credits"

**Diagnosis:**
- OpenAI account doesn't have available credits or billing isn't configured

**Solution:**
- Add payment method to OpenAI dashboard: https://platform.openai.com/account/billing/overview

### Issue: "Supabase FK constraint failed"

**Diagnosis:**
- Company doesn't exist in `companies` table before inserting call

**Solution:**
- Populate companies table first:
```bash
python3 ../call-scoring-agent/scripts/populate_companies_for_calls.py
```

## Performance Expectations

| Stage | Time | Cost |
|-------|------|------|
| Fetch Agent | <1s | $0 |
| Transcription (Deepgram) | <300ms | $0.0043/min |
| Clean Transcript (OpenAI) | 2-3s | $0.00015 |
| BANTIC Analysis (OpenAI) | 5-10s | $0.0005 |
| Score Module | <100ms | $0 |
| AE Brief (OpenAI gpt-4o) | 3-5s | $0.001 |
| **Total per call** | **12-20s** | **~$0.007** |
| **Total for 10 calls** | **2-3 min** | **~$0.07** |

## Next Steps

1. **Run one test cycle**: `python3 orchestrator.py --once`
2. **Monitor logs**: `tail -f logs/orchestrator.log`
3. **Check output**: `cat handoffs/*_handoff.md`
4. **Start continuous loop**: `python3 orchestrator.py`

## Support

For issues or questions:
- Check logs: `logs/orchestrator.log`
- Review BANTIC evidence in Supabase
- Compare with call-scoring-agent pipeline for reference

---

**Status**: Ready to deploy
**Last Updated**: 2026-04-28
