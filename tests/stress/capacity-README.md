# Isolated chat capacity laboratory

The capacity stack always uses Compose project `knowpliot-capacity`, port `18080`, and separately named PostgreSQL/Redis/Prometheus volumes. It never connects to the normal `knowpliot` database.

Run the two-minute smoke profile and remove only the isolated volumes:

```powershell
node tests/stress/run-capacity.mjs --profile smoke --cleanup
```

The exact profiles live in `capacity-profile.json`. Synthetic-provider reports are written to `artifacts/capacity/latest/summary.json` and `report.md`. A 500-stream synthetic result does not certify the real provider quota.

Real-provider sampling is rejected before network access unless all guards are present, and remains capped at 20 users, one turn each, 300 input characters, and 512 output tokens:

```powershell
$env:ENABLE_REAL_PROVIDER_STRESS='1'
$env:REAL_PROVIDER_MAX_USERS='20'
$env:DASHSCOPE_API_KEY='<temporary-key>'
node tests/stress/run-capacity.mjs --profile realProvider --cleanup
```

Never commit provider keys, JWTs, seeded passwords, or generated artifacts.
