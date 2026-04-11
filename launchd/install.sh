#!/bin/bash
#
# launchd/install.sh — one-shot installer for the energy-daily-digest
# launchd job.
#
# What it does:
#   1. Resolves the repo root from this script's location (no hardcoded paths)
#   2. Substitutes __REPO_ROOT__ in the plist template with the real path
#   3. Copies the resolved plist to ~/Library/LaunchAgents/
#   4. (optional) Copies the GEMINI_API_KEY export line from ~/.zshrc to
#      ~/.bash_profile, so launchd's `bash -l` can see it at fire time
#   5. Unloads any previous version (idempotent) then loads the new one
#   6. Verifies the job is registered via `launchctl list`
#
# Usage:
#   cd ~/code/tang-energy-feed
#   bash launchd/install.sh
#
# Uninstall:
#   launchctl unload ~/Library/LaunchAgents/com.tang.energy-daily-digest.plist
#   rm ~/Library/LaunchAgents/com.tang.energy-daily-digest.plist
#
# After installing, test manually first:
#   ./scripts/run.sh
#
# Then wait for the next 10:30 or 11:00 automatic trigger, and check logs:
#   tail -f /tmp/energy-daily-digest.log /tmp/energy-daily-digest.err

set -euo pipefail

# Resolve paths (works regardless of the caller's cwd)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEMPLATE="$SCRIPT_DIR/com.tang.energy-daily-digest.plist.template"
TARGET="$HOME/Library/LaunchAgents/com.tang.energy-daily-digest.plist"
LABEL="com.tang.energy-daily-digest"

echo "==========================================================="
echo "  energy-daily-digest launchd installer"
echo "==========================================================="
echo ""
echo "  Repo root: $REPO_ROOT"
echo "  Template:  $TEMPLATE"
echo "  Target:    $TARGET"
echo ""

# -----------------------------------------------------------------------------
# Pre-flight: check the template exists
# -----------------------------------------------------------------------------
if [ ! -f "$TEMPLATE" ]; then
    echo "✗ Template not found: $TEMPLATE"
    exit 1
fi

# -----------------------------------------------------------------------------
# Pre-flight: check that run.sh exists and is executable
# -----------------------------------------------------------------------------
if [ ! -x "$REPO_ROOT/scripts/run.sh" ]; then
    echo "✗ $REPO_ROOT/scripts/run.sh is not executable."
    echo "  Fix: chmod +x $REPO_ROOT/scripts/run.sh"
    exit 1
fi

# -----------------------------------------------------------------------------
# Pre-flight: check that config.json exists
# -----------------------------------------------------------------------------
if [ ! -f "$REPO_ROOT/config.json" ]; then
    echo "✗ $REPO_ROOT/config.json not found."
    echo "  Run: cp config.example.json config.json"
    echo "  Then edit config.json and set feishu.chat_id"
    exit 1
fi

# -----------------------------------------------------------------------------
# Step 1: Render the plist from the template
# -----------------------------------------------------------------------------
echo "▸ Step 1/4: Rendering plist from template"
mkdir -p "$(dirname "$TARGET")"
sed "s|__REPO_ROOT__|$REPO_ROOT|g" "$TEMPLATE" > "$TARGET"
echo "  ✓ Wrote $TARGET"

# -----------------------------------------------------------------------------
# Step 2: Make GEMINI_API_KEY visible to launchd's bash -l
# -----------------------------------------------------------------------------
# launchd uses `bash -l`, which sources /etc/profile and ~/.bash_profile
# but NOT ~/.zshrc. If GEMINI_API_KEY is only in ~/.zshrc, copy the line
# to ~/.bash_profile so launchd can see it.
echo ""
echo "▸ Step 2/4: Ensuring GEMINI_API_KEY is available to launchd"

if [ -z "${GEMINI_API_KEY:-}" ]; then
    echo "  ⚠ GEMINI_API_KEY is not set in the current shell."
    echo "    Run: source ~/.zshrc  (and re-run this installer)"
    echo "    Or set it manually before proceeding."
fi

NEEDS_BASH_PROFILE_UPDATE=0

# Check if ~/.bash_profile already has GEMINI_API_KEY
if [ ! -f ~/.bash_profile ] || ! grep -q "GEMINI_API_KEY" ~/.bash_profile 2>/dev/null; then
    NEEDS_BASH_PROFILE_UPDATE=1
fi

if [ $NEEDS_BASH_PROFILE_UPDATE -eq 1 ]; then
    # Check if ~/.zshrc has it (source of truth)
    if [ -f ~/.zshrc ] && grep -q "GEMINI_API_KEY" ~/.zshrc; then
        echo "  → Copying GEMINI_API_KEY export from ~/.zshrc to ~/.bash_profile"
        # Extract the exact export line (preserving the key value)
        ZSHRC_LINE=$(grep "^export GEMINI_API_KEY=" ~/.zshrc | tail -1)
        if [ -n "$ZSHRC_LINE" ]; then
            {
                echo ""
                echo "# Added by tang-energy-feed launchd installer ($(date '+%Y-%m-%d %H:%M'))"
                echo "# launchd's 'bash -l' reads this file, but not ~/.zshrc"
                echo "$ZSHRC_LINE"
            } >> ~/.bash_profile
            echo "  ✓ Appended to ~/.bash_profile"
        else
            echo "  ⚠ Could not extract export line from ~/.zshrc"
        fi
    else
        echo "  ⚠ GEMINI_API_KEY not found in ~/.zshrc either."
        echo "    launchd may not have access to the key at fire time."
        echo "    Fix: manually add it to ~/.bash_profile:"
        echo "      echo 'export GEMINI_API_KEY=\"…\"' >> ~/.bash_profile"
    fi
else
    echo "  ✓ ~/.bash_profile already has GEMINI_API_KEY"
fi

# -----------------------------------------------------------------------------
# Step 3: Unload any previous version (idempotent)
# -----------------------------------------------------------------------------
echo ""
echo "▸ Step 3/4: Unloading previous version if any"
if launchctl list | grep -q "$LABEL"; then
    launchctl unload "$TARGET" 2>/dev/null || true
    echo "  ✓ Unloaded previous $LABEL"
else
    echo "  ℹ No previous version loaded"
fi

# -----------------------------------------------------------------------------
# Step 4: Load the new plist
# -----------------------------------------------------------------------------
echo ""
echo "▸ Step 4/4: Loading new plist"
launchctl load "$TARGET"

# Verify it's registered
if launchctl list | grep -q "$LABEL"; then
    echo "  ✓ $LABEL is now registered with launchd"
else
    echo "  ✗ Failed to register $LABEL. Check logs:"
    echo "    tail /tmp/energy-daily-digest.err"
    exit 1
fi

# -----------------------------------------------------------------------------
# Done — print summary
# -----------------------------------------------------------------------------
echo ""
echo "==========================================================="
echo "  ✅ Installation complete"
echo "==========================================================="
echo ""
echo "  Schedule:  10:30 and 11:00 local time, every day"
echo "  Logs:      /tmp/energy-daily-digest.log"
echo "  Errors:    /tmp/energy-daily-digest.err"
echo ""
echo "  Next steps:"
echo "    1. Test manually: cd $REPO_ROOT && ./scripts/run.sh"
echo "    2. Wait for 10:30 local time, then check the logs:"
echo "       tail -f /tmp/energy-daily-digest.log"
echo "    3. Confirm the Feishu group received the card"
echo ""
echo "  To uninstall:"
echo "    launchctl unload $TARGET"
echo "    rm $TARGET"
echo ""
