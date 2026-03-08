#!/usr/bin/env bash
# Stress test suite for POS thermal print server
# Usage: ./stress_test.sh [host:port]

HOST="${1:-192.168.1.65:9100}"
PASS=0
FAIL=0
TOTAL=0

check() {
    local desc="$1" expected_code="$2" actual_code="$3" body="$4"
    TOTAL=$((TOTAL + 1))
    if [ "$actual_code" = "$expected_code" ]; then
        PASS=$((PASS + 1))
        printf "  [PASS] %s (HTTP %s)\n" "$desc" "$actual_code"
    else
        FAIL=$((FAIL + 1))
        printf "  [FAIL] %s — expected %s, got %s\n" "$desc" "$expected_code" "$actual_code"
        [ -n "$body" ] && printf "         %s\n" "$body"
    fi
}

run() {
    local desc="$1" expected="$2" method="$3" path="$4" content_type="$5" data="$6"
    local resp code body
    if [ "$method" = "GET" ]; then
        resp=$(curl -s -o /tmp/st_body -w "%{http_code}" --max-time 10 "http://$HOST$path")
    else
        resp=$(curl -s -o /tmp/st_body -w "%{http_code}" --max-time 10 \
            -X "$method" -H "Content-Type: $content_type" -d "$data" "http://$HOST$path")
    fi
    body=$(cat /tmp/st_body 2>/dev/null)
    check "$desc" "$expected" "$resp" "$body"
}

echo "========================================="
echo "POS Print Server Stress Test"
echo "Target: $HOST"
echo "========================================="

# --- 1. Health & basic endpoints ---
echo ""
echo "--- Basic Endpoints ---"
run "Health check" 200 GET "/health"
run "Web UI loads" 200 GET "/"
run "404 on unknown route" 404 GET "/nonexistent"

# --- 2. Valid print jobs (will actually print if printer connected!) ---
echo ""
echo "--- Valid Print Jobs ---"
run "Print message" 200 POST "/print/message" "application/json" \
    '{"text":"Stress test message","title":"TEST"}'

run "Print message no title" 200 POST "/print/message" "application/json" \
    '{"text":"Message without title"}'

run "Print label" 200 POST "/print/label" "application/json" \
    '{"heading":"STRESS TEST","lines":["Line 1","Line 2","Line 3"]}'

run "Print list" 200 POST "/print/list" "application/json" \
    '{"title":"Test List","rows":[["Item A","1.00"],["Item B","2.50"]]}'

run "Print receipt" 200 POST "/print/receipt" "application/json" \
    '{"items":[{"name":"Coffee","qty":2,"price":5.0},{"name":"Tea","qty":1,"price":3.0}]}'

run "Print dictionary" 200 POST "/print/dictionary" "application/json" \
    '{"word":"Resilience","definition":"The capacity to recover quickly from difficulties."}'

run "Print markdown" 200 POST "/print/markdown" "application/json" \
    '{"text":"# Stress Test\n\nThis is **bold** and *italic*.\n\n- Item 1\n- Item 2\n\n> A blockquote\n\n---\n\nDone."}'

# --- 3. Malformed / missing data ---
echo ""
echo "--- Malformed Input ---"
run "Message: missing text field" 500 POST "/print/message" "application/json" \
    '{"title":"no text"}'

run "Message: empty body" 500 POST "/print/message" "application/json" \
    '{}'

run "Label: missing heading" 500 POST "/print/label" "application/json" \
    '{"lines":["orphan line"]}'

run "List: missing rows" 500 POST "/print/list" "application/json" \
    '{"title":"No rows"}'

run "Receipt: empty items" 200 POST "/print/receipt" "application/json" \
    '{"items":[]}'

run "Dictionary: empty object" 500 POST "/print/dictionary" "application/json" \
    '{}'

run "Markdown: missing text" 500 POST "/print/markdown" "application/json" \
    '{}'

run "Invalid JSON" 400 POST "/print/message" "application/json" \
    'not json at all{{{}'

run "Empty POST body" 400 POST "/print/message" "application/json" \
    ''

# --- 4. Edge cases ---
echo ""
echo "--- Edge Cases ---"
run "Very long message" 200 POST "/print/message" "application/json" \
    "{\"text\":\"$(python3 -c "print('A'*5000)")\"}"

run "Unicode message" 200 POST "/print/message" "application/json" \
    '{"text":"Ünïcödé tëst: äöü ñ 你好 🎉 émojis","title":"UNICODE"}'

run "Special chars in label" 200 POST "/print/label" "application/json" \
    '{"heading":"<script>alert(1)</script>","lines":["&amp;","\"quotes\""]}'

run "Markdown with code block" 200 POST "/print/markdown" "application/json" \
    '{"text":"# Code\n\n```python\nprint(\"hello\")\n```\n\nEnd."}'

run "Newlines in message" 200 POST "/print/message" "application/json" \
    '{"text":"Line1\nLine2\nLine3\nLine4\nLine5"}'

# --- 5. Portrait endpoints (should return 501 without numpy) ---
echo ""
echo "--- Portrait (expect 501 without numpy) ---"
run "Portrait capture without numpy" 501 POST "/portrait/capture" "application/json" \
    '{}'

run "Portrait transform without numpy" 501 POST "/portrait/transform" "application/json" \
    '{}'

# --- 6. Wrong methods ---
echo ""
echo "--- Wrong HTTP Methods ---"
run "GET on POST endpoint" 405 GET "/print/message"
run "GET on print/receipt" 405 GET "/print/receipt"

# --- 7. Rapid fire (10 quick requests) ---
echo ""
echo "--- Rapid Fire (10 messages) ---"
for i in $(seq 1 10); do
    run "Rapid message #$i" 200 POST "/print/message" "application/json" \
        "{\"text\":\"Rapid fire $i/10\",\"title\":\"RAPID\"}"
done

# --- 8. Large payload ---
echo ""
echo "--- Large Payloads ---"
BIG_ROWS=$(python3 -c "import json; print(json.dumps([[f'Item {i}', f'{i}.00'] for i in range(100)]))")
run "List with 100 rows" 200 POST "/print/list" "application/json" \
    "{\"title\":\"Big List\",\"rows\":$BIG_ROWS}"

BIG_MD=$(python3 -c "print('# Big Doc\n\n' + '\n\n'.join([f'## Section {i}\n\nParagraph {i} with some text.' for i in range(50)]))")
run "Markdown 50 sections" 200 POST "/print/markdown" "application/json" \
    "{\"text\":$(python3 -c "import json; print(json.dumps('$BIG_MD'))" 2>/dev/null || echo '""')}"

# --- 9. Concurrent requests ---
echo ""
echo "--- Concurrent Requests (5 parallel) ---"
for i in $(seq 1 5); do
    curl -s -o /dev/null -w "  Concurrent #$i: HTTP %{http_code}\n" --max-time 30 \
        -X POST -H "Content-Type: application/json" \
        -d "{\"text\":\"Concurrent $i\",\"title\":\"PARALLEL\"}" \
        "http://$HOST/print/message" &
done
wait
echo "  (All concurrent requests completed)"

# --- 10. Check server is still alive ---
echo ""
echo "--- Post-Stress Health Check ---"
sleep 2
run "Server still alive" 200 GET "/health"

# --- Summary ---
echo ""
echo "========================================="
echo "RESULTS: $PASS passed, $FAIL failed, $TOTAL total"
echo "========================================="

rm -f /tmp/st_body
