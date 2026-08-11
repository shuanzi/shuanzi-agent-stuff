# Verification Record

Release: `1.0.0`  
Date: `2026-07-22`

The release package was verified with the following checks:

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q bin tests
bash -n install.sh uninstall.sh examples/send-test.sh
python3 -m json.tool config/config.example.json
python3 -m json.tool examples/stop-event.json
```

Result at packaging time:

- 19 unit/integration tests passed.
- Python bytecode compilation passed.
- Bash syntax validation passed.
- All distributed JSON examples passed parsing; installer tests cover user-level `hooks.json` merging.
- The HTTP integration test used a local temporary server and did not call a real Feishu endpoint.
