# Code Reference: Real QwenPaw Integration

## Critical Code Changes

### 1. Added Imports
```python
import json                    # Line 6 - NEW
from pathlib import Path       # Line 8 - NEW
```

### 2. Updated execute_case() - Line 60
```python
# OLD: success = self._simulate_execution(case, trace)
# NEW: Now unpacks tuple
success, final_answer = self._simulate_execution(case, trace)
```

### 3. Method Signature - Line 83
```python
# OLD: def _simulate_execution(...) -> bool:
# NEW: Returns tuple
def _simulate_execution(self, case: GAIACase, trace: ExecutionTrace) -> tuple[bool, Optional[str]]:
```

### 4. SSE Event Parsing - Line 173
```python
# This is the KEY line that parses SSE format
event_data = json.loads(line[6:])  # Remove "data: " prefix
```

### 5. Event Handling - Lines 176-203

**Text Events (Line 176-178)**:
```python
if event_data.get('type') == 'text':
    full_response += event_data.get('content', '')
    logger.debug(f"收到文本块: {event_data.get('content', '')[:100]}")
```

**Tool Call Events (Line 180-188)**:
```python
elif event_data.get('type') == 'tool_call':
    tool_name = event_data.get('tool_name', 'unknown')
    tool_args = event_data.get('arguments', {})
    self.collector.record_tool_call(iteration, tool_name, tool_args)
    logger.info(f"工具调用: {tool_name}")
```

**Tool Result Events (Line 190-200)**:
```python
elif event_data.get('type') == 'tool_result':
    tool_name = event_data.get('tool_name', 'unknown')
    result = event_data.get('result', '')
    status = event_data.get('status', 'success')
    self.collector.record_tool_result(iteration, tool_name, result, status)
    logger.info(f"工具结果: {tool_name} - {status}")
```

### 6. Answer Validation - Line 223
```python
# Compare response with expected answer
expected_answer = case.final_answer.lower()
actual_answer = full_response.lower()
success = expected_answer in actual_answer or actual_answer in expected_answer
```

### 7. Return Statement - Line 225
```python
# Return tuple instead of bool
return success, full_response
```

## Request Format

```json
{
  "input": [{"role": "user", "content": [
    {"type": "text", "text": "Question"},
    {"type": "file", "file_name": "doc.pdf", "file_path": "/path"}
  ]}],
  "session_id": "gaia-{task_id}"
}
```

## SSE Response Format

```
data: {"type": "text", "content": "..."}
data: {"type": "tool_call", "tool_name": "...", "arguments": {...}}
data: {"type": "tool_result", "tool_name": "...", "result": "...", "status": "success"}
data: {"type": "finish"}
```

## API Endpoint

`POST http://127.0.0.1:8089/api/console/chat`

**Auth**: Basic (admin:88888888)  
**Stream**: True  
**Timeout**: 300 seconds
