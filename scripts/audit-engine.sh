#!/bin/bash
# ==============================================================================
# Audit Engine - Pre-Release Security & Integrity Scan
# ==============================================================================

set -e

echo "🔍 Starting Pre-Release Audit..."

# Check if staged diff exists
if [ ! -f "staged_diff.tmp" ]; then
    echo "⚠️  No staged diff file found. Skipping diff-based audit."
    exit 0
fi

# Basic security checks
echo "✓ Checking for sensitive data patterns..."

# Check for common secrets patterns
if grep -E "(password|secret|token|api[_-]?key|private[_-]?key)" staged_diff.tmp; then
    echo "❌ Potential secrets detected in diff!"
    exit 1
fi

echo "✓ No obvious secrets detected"
echo "✓ Audit passed successfully"
exit 0
