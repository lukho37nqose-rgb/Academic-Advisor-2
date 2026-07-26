#!/bin/bash

# CI Gate: Enforce Domain Agnosticism in the Core Layer
# If any domain-specific language leaks into app/core, the build fails.

BANNED_WORDS=("student" "faculty" "curriculum" "nqf" "grant" "applicant" "vendor" "procurement")
CORE_DIR="app/core"

echo "Checking $CORE_DIR for domain leakage..."

FAIL=0

for word in "${BANNED_WORDS[@]}"; do
    # Search recursively, case-insensitive, returning file and line number
    MATCHES=$(grep -r -i -n "$word" "$CORE_DIR" || true)
    
    if [ ! -z "$MATCHES" ]; then
        echo "❌ ERROR: Found banned domain word '$word' in core layer:"
        echo "$MATCHES"
        FAIL=1
    fi
done

if [ $FAIL -eq 1 ]; then
    echo "🚨 CI FAILED: The Core abstraction layer has been compromised by domain-specific language."
    exit 1
else
    echo "✅ CI PASSED: No domain leakage found in the Core layer."
    exit 0
fi
