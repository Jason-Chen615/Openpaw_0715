# GAIA Runner - Real QwenPaw Integration Guide

## Quick Summary

The GAIA_Runner has been updated to send **real questions to QwenPaw** instead of simulating execution. It now:

1. ✅ Connects to running QwenPaw Docker container at `http://127.0.0.1:8089/api`
2. ✅ Sends GAIA questions with attachments via HTTP POST to `/api/console/chat`
3. ✅ Receives and parses Server-Sent Events (SSE) stream
4. ✅ Records tool calls, tool results, and text responses
5. ✅ Saves complete execution traces to JSON files
6. ✅ Generates analysis reports

## What Changed

### Before (Simulated)
```python
# agent_runner.py - OLD
def _simulate_execution(self, case: GAIACase, trace: ExecutionTrace) -> bool:
    time.sleep(0.5)  # Just wait 0.5 seconds
    return True      # Always return True
```

### After (Real)
```python
# agent_runner.py - NEW
def _simulate_execution(self, case: GAIACase, trace: ExecutionTrace) -> tuple[bool, Optional[str]]:
    # Send POST to http://127.0.0.1:8089/api/console/chat
    # Parse SSE stream events
    # Record tool calls, results, text chunks
    # Return (success_flag, full_response_text)
    return success, full_response
```

## How to Run

```bash
cd d:\Huawei_Code\QwenPaw

python GAIA_Runner/scripts/run_three_cases.py \
  --output-dir GAIA_Runner/outputs \
  --dataset-root dataset/GAIA \
  --qwenpaw-url http://127.0.0.1:8089/api \
  --api-user admin \
  --api-pass 88888888
```

## Output Files

After execution, check:
- **Traces**: `GAIA_Runner/outputs/traces/{case_id}_level{N}.jsonl` - Raw event stream
- **Reports**: `GAIA_Runner/outputs/reports/analysis_report.html` - Summary report
- **Logs**: `GAIA_Runner/outputs/logs/gaia_runner.log` - Detailed log

## Key Implementation Details

### Request Format
```json
{
  "input": [
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "Question text"},
        {"type": "file", "file_name": "doc.pdf", "file_path": "/path/to/file"}
      ]
    }
  ],
  "session_id": "gaia-{task_id}"
}
```

### SSE Event Types
- `{"type": "text", "content": "..."}` - Text response chunk
- `{"type": "tool_call", "tool_name": "...", "arguments": {...}}` - Tool invocation
- `{"type": "tool_result", "tool_name": "...", "result": "...", "status": "success"}` - Tool result
- `{"type": "finish"}` - Stream end

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| Connection refused | QwenPaw not running | `docker ps` and check container status |
| 401 Unauthorized | Wrong credentials | Verify `admin:88888888` |
| Invalid JSON in SSE | API format mismatch | Check QwenPaw version |
| File not found | Dataset missing | Ensure `dataset/GAIA/2023/` exists |

## File Modified

`d:\Huawei_Code\QwenPaw\GAIA_Runner\runner\agent_runner.py`

Main changes:
- Added `json` import
- Added `Path` import  
- Updated `execute_case()` to unpack tuple return
- Replaced entire `_simulate_execution()` method with real API logic
- Integrated SSE stream parsing
- Added event recording for each event type
