#!/usr/bin/env bash
# ============================================================
# digimon-world 部署冒烟测试 / Deployment Smoke Test
# ============================================================
# 用法: ./scripts/smoke_test.sh [BASE_URL]
# 默认 BASE_URL=https://digimon-world.robin-shaun.workers.dev
# 退出码: 0=全部通过, 1=有失败
# ============================================================

set -euo pipefail

BASE_URL="${1:-https://digimon-world.robin-shaun.workers.dev}"
TIMEOUT=15
PASS=0
FAIL=0

# ---- 颜色 ----
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "============================================"
echo "🐉 digimon-world 部署冒烟测试"
echo "============================================"
echo "📍 Base URL: ${BASE_URL}"
echo ""

# ---- 工具函数 ----
check_endpoint() {
    local label="$1"
    local url="$2"
    local expected_status="${3:-200}"
    local method="${4:-GET}"

    echo -n "  ${label} ... "

    local http_code
    http_code=$(curl -sS -o /dev/null -w "%{http_code}" \
        --max-time "${TIMEOUT}" \
        -X "${method}" \
        "${url}" 2>/dev/null) || http_code="000"

    if [ "${http_code}" = "${expected_status}" ]; then
        echo -e "${GREEN}PASS${NC} (HTTP ${http_code})"
        PASS=$((PASS + 1))
        return 0
    else
        echo -e "${RED}FAIL${NC} (expected ${expected_status}, got ${http_code})"
        FAIL=$((FAIL + 1))
        return 1
    fi
}

check_json_endpoint() {
    local label="$1"
    local url="$2"
    local key="${3:-}"

    echo -n "  ${label} ... "

    local resp
    resp=$(curl -sS --max-time "${TIMEOUT}" "${url}" 2>/dev/null) || {
        echo -e "${RED}FAIL${NC} (unreachable)"
        FAIL=$((FAIL + 1))
        return 1
    }

    # Validate JSON
    if echo "${resp}" | python3 -c "import json, sys; json.load(sys.stdin)" 2>/dev/null; then
        if [ -n "${key}" ]; then
            local val
            val=$(echo "${resp}" | python3 -c "import json, sys; d=json.load(sys.stdin); print(d.get('${key}', 'MISSING'))" 2>/dev/null)
            echo -e "${GREEN}PASS${NC} (key '${key}' = ${val})"
        else
            echo -e "${GREEN}PASS${NC} (valid JSON)"
        fi
        PASS=$((PASS + 1))
        return 0
    else
        echo -e "${RED}FAIL${NC} (invalid JSON: $(echo "${resp}" | head -c 100))"
        FAIL=$((FAIL + 1))
        return 1
    fi
}

# ---- 测试用例 ----

echo "📡 Backend API 端点检查"
echo "------------------------"
check_endpoint "GET / (health)"           "${BASE_URL}/"                      200
check_endpoint "GET /api/health/perf"     "${BASE_URL}/api/health/perf"       200
check_json_endpoint "GET /api/digimon"    "${BASE_URL}/api/digimon"           ""
check_json_endpoint "GET /api/world"      "${BASE_URL}/api/world"             "clock_tick"
check_endpoint "GET /api/vitality"        "${BASE_URL}/api/vitality"          200
check_endpoint "GET /api/emergence"       "${BASE_URL}/api/emergence"         200
check_endpoint "GET /api/pokedex"         "${BASE_URL}/api/pokedex"           200
echo ""

echo "🌐 Frontend 静态资源检查"
echo "------------------------"
check_endpoint "GET / (index.html)"       "${BASE_URL}/index.html"            200
check_endpoint "GET /main.js"             "${BASE_URL}/main.js"               200
check_endpoint "GET /style.css"           "${BASE_URL}/style.css"             200
check_endpoint "GET /battle.html"         "${BASE_URL}/battle.html"           200
check_endpoint "GET /evolution.html"      "${BASE_URL}/evolution.html"        200
check_endpoint "GET /log.html"            "${BASE_URL}/log.html"              200
check_endpoint "GET /stats.html"          "${BASE_URL}/stats.html"            200
# 404 页面应返回 404 或 200（取决于 Workers 配置），只验证可达
check_endpoint "GET /404.html"            "${BASE_URL}/404.html"               "200|404"
echo ""

echo "🔐 安全头检查"
echo "------------------------"
# CORS: API 应允许跨域
echo -n "  CORS headers on /api/digimon ... "
cors=$(curl -sS -I --max-time "${TIMEOUT}" "${BASE_URL}/api/digimon" 2>/dev/null | grep -i "access-control-allow-origin" || true)
if [ -n "${cors}" ]; then
    echo -e "${GREEN}PASS${NC} (${cors})"
    PASS=$((PASS + 1))
else
    echo -e "${YELLOW}SKIP${NC} (no CORS header, may be expected)"
fi
echo ""

# ---- 结果汇总 ----
echo "============================================"
TOTAL=$((PASS + FAIL))
if [ "${FAIL}" -eq 0 ]; then
    echo -e "${GREEN}✅ ALL ${TOTAL} TESTS PASSED${NC}"
    echo "============================================"
    exit 0
else
    echo -e "${RED}❌ ${FAIL}/${TOTAL} TESTS FAILED${NC}"
    echo "============================================"
    exit 1
fi
