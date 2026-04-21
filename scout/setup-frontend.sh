#!/usr/bin/env bash
# =============================================================================
# setup-frontend.sh – Bootstrap the React frontend for local development
#
# Usage: ./setup-frontend.sh [API_ENDPOINT]
#
# API_ENDPOINT should include the /api prefix, e.g.:
#   ./setup-frontend.sh https://scout-api.andreas.services/api
# =============================================================================
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="${PROJECT_ROOT}/frontend"
API_ENDPOINT="${1:-http://localhost:3001/api}"

echo "Setting up Scout Events frontend..."
echo "  API endpoint: ${API_ENDPOINT}"

cd "${FRONTEND_DIR}"

echo "Installing npm dependencies..."
npm install

cat > .env.local << EOF
VITE_API_URL=${API_ENDPOINT}
VITE_BASE=/app/
EOF

echo "  Wrote .env.local"
echo
echo "Done! Start the dev server with:"
echo "  cd frontend && npm run dev"
