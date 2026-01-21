#!/bin/bash
#
# Setup Script for Nate Level 2 Execution Environment
#
# This script configures the system for safe command execution:
# - Creates audit log directory with proper permissions
# - Sets up Git configuration for automated commits
# - Optionally creates a restricted user for execution
#
# Usage: sudo ./setup_level2_execution.sh [--create-user]

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
AUDIT_LOG_DIR="/var/log"
AUDIT_LOG_FILE="/var/log/nate_dev_commands.log"
AICARA_ROOT="/opt/aicara"
CREATE_USER=false

# Parse arguments
if [[ "$1" == "--create-user" ]]; then
    CREATE_USER=true
fi

echo -e "${GREEN}=== Nate Level 2 Setup ===${NC}"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Error: This script must be run as root${NC}"
    echo "Usage: sudo $0 [--create-user]"
    exit 1
fi

echo -e "${YELLOW}[1/5] Creating audit log directory...${NC}"
# Create audit log file and set permissions
touch "$AUDIT_LOG_FILE"
chmod 644 "$AUDIT_LOG_FILE"
echo -e "${GREEN}✓ Audit log created: $AUDIT_LOG_FILE${NC}"

echo ""
echo -e "${YELLOW}[2/5] Verifying /opt/aicara access...${NC}"
if [ ! -d "$AICARA_ROOT" ]; then
    echo -e "${RED}Error: $AICARA_ROOT does not exist${NC}"
    exit 1
fi
echo -e "${GREEN}✓ $AICARA_ROOT exists${NC}"

echo ""
echo -e "${YELLOW}[3/5] Checking Git configuration...${NC}"
# Check if git is installed
if ! command -v git &> /dev/null; then
    echo -e "${RED}Error: git is not installed${NC}"
    echo "Install with: apt-get install git"
    exit 1
fi
echo -e "${GREEN}✓ Git is installed${NC}"

# Check if gh CLI is installed (optional)
if command -v gh &> /dev/null; then
    echo -e "${GREEN}✓ GitHub CLI (gh) is installed${NC}"
else
    echo -e "${YELLOW}  GitHub CLI (gh) not found - PR creation will not be available${NC}"
    echo "  Install with: https://cli.github.com/"
fi

echo ""
echo -e "${YELLOW}[4/5] Setting up Git configuration...${NC}"
# Configure git for Nate's commits if not already configured
SUBSTRATE_DIR="$AICARA_ROOT/nate_api_substrate"
if [ -d "$SUBSTRATE_DIR/.git" ]; then
    cd "$SUBSTRATE_DIR"

    # Check if user email is configured
    if ! git config user.email &> /dev/null; then
        echo "Configuring git user for Nate's commits..."
        git config user.name "Nate AI"
        git config user.email "nate@aicara.local"
        echo -e "${GREEN}✓ Git user configured${NC}"
    else
        echo -e "${GREEN}✓ Git already configured${NC}"
    fi
else
    echo -e "${YELLOW}  Warning: Git repository not found at $SUBSTRATE_DIR${NC}"
fi

echo ""
if [ "$CREATE_USER" = true ]; then
    echo -e "${YELLOW}[5/5] Creating restricted user 'nate-exec'...${NC}"

    # Check if user already exists
    if id "nate-exec" &>/dev/null; then
        echo -e "${YELLOW}  User 'nate-exec' already exists, skipping...${NC}"
    else
        # Create system user without home directory
        useradd -r -s /bin/bash -d /opt/aicara nate-exec

        # Add to necessary groups
        usermod -aG systemd-journal nate-exec  # For reading logs

        echo -e "${GREEN}✓ User 'nate-exec' created${NC}"
    fi

    # Set up permissions for the user
    echo "Setting up permissions for nate-exec..."
    # Allow read access to /opt/aicara
    chmod -R o+r "$AICARA_ROOT" || true
    # Allow write access to audit log
    chown root:nate-exec "$AUDIT_LOG_FILE"
    chmod 664 "$AUDIT_LOG_FILE"

    echo -e "${GREEN}✓ Permissions configured${NC}"
else
    echo -e "${YELLOW}[5/5] Skipping user creation (use --create-user to enable)${NC}"
    echo "  Running as current user with existing permissions"
fi

echo ""
echo -e "${GREEN}=== Setup Complete ===${NC}"
echo ""
echo "Level 2 execution environment is ready!"
echo ""
echo "Configuration:"
echo "  - Audit log: $AUDIT_LOG_FILE"
echo "  - Allowed root: $AICARA_ROOT"
echo "  - Rate limit: 5 commands per 60 seconds"
echo ""
echo "Next steps:"
echo "  1. Test with dry_run: nate_dev_tool(action='execute_command', command='ls -la', dry_run=True)"
echo "  2. View whitelist: nate_dev_tool(action='get_command_whitelist')"
echo "  3. Check audit logs: nate_dev_tool(action='get_audit_logs')"
echo ""
if ! command -v gh &> /dev/null; then
    echo -e "${YELLOW}Optional: Install GitHub CLI for PR automation:${NC}"
    echo "  curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg"
    echo "  echo \"deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main\" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null"
    echo "  sudo apt update"
    echo "  sudo apt install gh"
    echo "  gh auth login"
    echo ""
fi
