#!/usr/bin/env bash
# =============================================================================
# setup-frontend.sh – Bootstrap the React frontend for local development
#
# Usage: ./setup-frontend.sh [API_ENDPOINT]
# =============================================================================
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="${PROJECT_ROOT}/frontend"
API_ENDPOINT="${1:-http://localhost:3001}"

echo "Setting up NYC Events frontend..."
echo "  API endpoint: ${API_ENDPOINT}"

cd "${FRONTEND_DIR}"

# Install dependencies
echo "Installing npm dependencies..."
npm install

# Write .env.local with the API URL
cat > .env.local << EOF
REACT_APP_API_URL=${API_ENDPOINT}
EOF

echo "  Wrote .env.local"
echo
echo "Done! Start development server with:"
echo "  cd frontend && npm start"
