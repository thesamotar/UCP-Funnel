#!/usr/bin/env bash
# Start all three services: mock BigBasket (9001), mock Croma (9002), Tata UCP node + frontend (8000)
cd "$(dirname "$0")"
[ -f .env ] && set -a && source .env && set +a
PY=python3
[ -x .venv/bin/python ] && PY=.venv/bin/python
trap 'kill 0' EXIT

$PY -m uvicorn mocks.bigbasket.app:app --port 9001 &
$PY -m uvicorn mocks.croma.app:app --port 9002 &
$PY -m uvicorn mocks.zudio.app:app --port 9003 &
$PY -m uvicorn mocks.cliq.app:app --port 9004 &
$PY -m uvicorn mocks.onemg.app:app --port 9005 &
$PY -m uvicorn mocks.titan.app:app --port 9006 &
$PY -m uvicorn mocks.ihcl.app:app --port 9007 &
$PY -m uvicorn mocks.airindia.app:app --port 9008 &
$PY -m uvicorn wrapper.main:app --port 8000 &
echo ""
echo "  Tata UCP demo → http://localhost:8000"
echo ""
wait
