#!/usr/bin/env bash
# Submit PRD Triage Agent to GitHub.
# Usage:
#   bash scripts/submit.sh                                    # commit only
#   bash scripts/submit.sh https://github.com/USER/repo.git   # commit + push
set -euo pipefail

echo "=== Step 1: Verify staging ==="
STAGED=$(git diff --cached --name-only | wc -l | tr -d ' ')
if [ "$STAGED" -eq 0 ]; then
    echo "No files staged. Running git add -A..."
    git add -A
    STAGED=$(git diff --cached --name-only | wc -l | tr -d ' ')
fi
echo "  $STAGED files staged ✅"

echo ""
echo "=== Step 2: Commit ==="
git commit -m "feat: PRD Triage Agent — multi-agent PRD intake checkup for Google x Kaggle Capstone 2026

- 8 ADK agents (completeness, clarity, architecture, risk, synthesis, orchestrator, estimation, breakdown)
- Document MCP server (4 tools, stdio transport, embedding cache)
- Policy gate (10 regex rules, human-reviewable YAML)
- HITL gate + critical-risk deterministic veto
- FastAPI server + Dockerfile + cloudflared deployment
- prd-analysis custom Skill (Level 3)
- 121 tests, 30/30 Spectra tasks, Spec-Driven Development" 2>/dev/null || echo "  (already committed or nothing to commit)"

REMOTE_URL="${1:-}"

if [ -z "$REMOTE_URL" ]; then
    echo ""
    echo "✅ Committed! Next steps:"
    echo ""
    echo "  1. Go to https://github.com/new"
    echo "     Repository name: prd-triage-agent"
    echo "     Visibility: Public"
    echo "     Do NOT initialize with README/license/gitignore"
    echo ""
    echo "  2. Copy the repo URL and run:"
    echo "     git remote add origin https://github.com/YOUR_USERNAME/prd-triage-agent.git"
    echo "     git push -u origin main"
    echo ""
    echo "  3. Upload assets/demo_video.mp4 to YouTube (set as PUBLIC)"
    echo ""
    echo "  4. Submit on Kaggle:"
    echo "     - Paste WRITEUP.md content"
    echo "     - Upload assets/cover.png (cover image)"
    echo "     - Upload assets/architecture.png"
    echo "     - Add YouTube + GitHub links"
    echo "     - Select track: Agents for Business"
    echo "     - Click Submit"
    exit 0
fi

echo ""
echo "=== Step 3: Push to GitHub ==="
git remote remove origin 2>/dev/null || true
git remote add origin "$REMOTE_URL"
git push -u origin main
echo ""
echo "✅ Pushed to $REMOTE_URL"
