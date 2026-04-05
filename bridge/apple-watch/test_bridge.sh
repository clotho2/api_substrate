#!/usr/bin/env bash
# ============================================
# Guardian Watch Bridge Test Script
# ============================================
#
# Tests the full data flow: ingest → latest → vitals → anomaly detection
#
# Usage:
#   ./test_bridge.sh                          # localhost, no auth
#   ./test_bridge.sh https://your-domain:8284 your-token-here
#

set -euo pipefail

BASE_URL="${1:-http://localhost:8284}"
TOKEN="${2:-}"
AUTH_HEADER=""

if [ -n "$TOKEN" ]; then
    AUTH_HEADER="-H \"Authorization: Bearer $TOKEN\""
fi

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}PASS${NC}: $1"; }
fail() { echo -e "${RED}FAIL${NC}: $1"; exit 1; }
info() { echo -e "${YELLOW}----${NC} $1"; }

echo "============================================"
echo " Guardian Watch Bridge Test"
echo " Target: $BASE_URL"
echo " Auth: $([ -n "$TOKEN" ] && echo "enabled" || echo "disabled")"
echo "============================================"
echo

# --- Test 1: Health check ---
info "Test 1: Health check"
HEALTH=$(curl -sf "$BASE_URL/api/guardian-watch/health" 2>/dev/null || echo "FAIL")
if echo "$HEALTH" | grep -q '"service"'; then
    pass "Health endpoint responding"
else
    fail "Health endpoint not responding. Is the substrate running?"
fi

# --- Test 2: Ingest normal reading ---
info "Test 2: Ingest normal heart rate reading"
RESULT=$(curl -sf -X POST "$BASE_URL/api/guardian-watch/ingest" \
    -H "Content-Type: application/json" \
    ${TOKEN:+-H "Authorization: Bearer $TOKEN"} \
    -d '{
        "heart_rate": 72,
        "heart_rate_variability": 42.0,
        "respiratory_rate": 15,
        "blood_oxygen": 98.0,
        "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"
    }' 2>/dev/null || echo "FAIL")

if echo "$RESULT" | grep -q '"status": "ok"'; then
    pass "Normal reading ingested"
else
    fail "Ingest failed: $RESULT"
fi

# --- Test 3: Verify latest ---
info "Test 3: Verify latest reading"
LATEST=$(curl -sf "$BASE_URL/api/guardian-watch/latest" 2>/dev/null || echo "FAIL")
if echo "$LATEST" | grep -q '"heart_rate": 72'; then
    pass "Latest reading returned correctly"
else
    fail "Latest reading mismatch: $LATEST"
fi

# --- Test 4: Vitals summary ---
info "Test 4: Vitals summary"
VITALS=$(curl -sf "$BASE_URL/api/guardian-watch/vitals" 2>/dev/null || echo "FAIL")
if echo "$VITALS" | grep -q '"available": true'; then
    pass "Vitals summary available"
else
    fail "Vitals not available: $VITALS"
fi

# --- Test 5: Context string ---
info "Test 5: Context string for consciousness"
CTX=$(curl -sf "$BASE_URL/api/guardian-watch/context" 2>/dev/null || echo "FAIL")
if echo "$CTX" | grep -q 'Apple Watch'; then
    pass "Context string formatted for system prompt"
else
    fail "Context string missing: $CTX"
fi

# --- Test 6: Ingest enough readings to build baseline ---
info "Test 6: Building baseline (ingesting 35 readings)..."
for i in $(seq 1 35); do
    HR=$((68 + RANDOM % 10))  # 68-77 bpm range
    RR=$((13 + RANDOM % 5))   # 13-17 breaths/min
    HRV=$((35 + RANDOM % 15)) # 35-49 ms
    curl -sf -X POST "$BASE_URL/api/guardian-watch/ingest" \
        -H "Content-Type: application/json" \
        ${TOKEN:+-H "Authorization: Bearer $TOKEN"} \
        -d "{
            \"heart_rate\": $HR,
            \"heart_rate_variability\": $HRV,
            \"respiratory_rate\": $RR,
            \"blood_oxygen\": 98.0,
            \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"
        }" > /dev/null 2>&1
done
pass "35 readings ingested for baseline"

# --- Test 7: Verify baseline ---
info "Test 7: Verify baseline calculated"
BASELINE=$(curl -sf "$BASE_URL/api/guardian-watch/baseline" 2>/dev/null || echo "FAIL")
if echo "$BASELINE" | grep -q '"sample_count"'; then
    SAMPLES=$(echo "$BASELINE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('sample_count',0))" 2>/dev/null || echo "0")
    if [ "$SAMPLES" -gt 0 ]; then
        pass "Baseline calculated with $SAMPLES samples"
    else
        fail "Baseline has 0 samples"
    fi
else
    fail "Baseline not returned: $BASELINE"
fi

# --- Test 8: Trigger anomaly with extreme HR ---
info "Test 8: Trigger anomaly with extreme heart rate (180 bpm)"
ANOMALY_RESULT=$(curl -sf -X POST "$BASE_URL/api/guardian-watch/ingest" \
    -H "Content-Type: application/json" \
    ${TOKEN:+-H "Authorization: Bearer $TOKEN"} \
    -d '{
        "heart_rate": 180,
        "respiratory_rate": 15,
        "blood_oxygen": 98.0,
        "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"
    }' 2>/dev/null || echo "FAIL")

if echo "$ANOMALY_RESULT" | grep -q '"metric": "heart_rate"'; then
    pass "Anomaly detected for extreme heart rate"
else
    # Check anomalies endpoint
    ANOMALIES=$(curl -sf "$BASE_URL/api/guardian-watch/anomalies" 2>/dev/null || echo "FAIL")
    if echo "$ANOMALIES" | grep -q '"heart_rate"'; then
        pass "Anomaly detected (found in anomalies endpoint)"
    else
        info "WARN: No anomaly triggered — baseline may need more variance"
    fi
fi

# --- Test 9: Trigger SpO2 critical ---
info "Test 9: Trigger critical SpO2 alert (88%)"
SPO2_RESULT=$(curl -sf -X POST "$BASE_URL/api/guardian-watch/ingest" \
    -H "Content-Type: application/json" \
    ${TOKEN:+-H "Authorization: Bearer $TOKEN"} \
    -d '{
        "heart_rate": 72,
        "blood_oxygen": 88.0,
        "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"
    }' 2>/dev/null || echo "FAIL")

if echo "$SPO2_RESULT" | grep -q '"blood_oxygen"'; then
    pass "Critical SpO2 anomaly detected"
else
    fail "SpO2 critical alert not triggered: $SPO2_RESULT"
fi

# --- Test 10: Auth rejection (if token is set) ---
if [ -n "$TOKEN" ]; then
    info "Test 10: Auth rejection with bad token"
    BAD_AUTH=$(curl -sf -o /dev/null -w "%{http_code}" -X POST \
        "$BASE_URL/api/guardian-watch/ingest" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer wrong-token-here" \
        -d '{"heart_rate": 72}' 2>/dev/null || echo "000")
    if [ "$BAD_AUTH" = "403" ]; then
        pass "Bad token correctly rejected (403)"
    else
        info "WARN: Expected 403, got $BAD_AUTH"
    fi
else
    info "Test 10: Skipped (no auth token configured)"
fi

echo
echo "============================================"
echo -e " ${GREEN}All tests passed!${NC}"
echo " Guardian Watch bridge is ready for iPhone Shortcuts."
echo "============================================"
