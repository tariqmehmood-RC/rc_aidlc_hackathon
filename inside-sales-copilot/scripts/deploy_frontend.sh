#!/usr/bin/env bash
# Build the production frontend, write config.json from the stack outputs, upload it to the
# site bucket, and invalidate CloudFront (task 5.7). Run after `cdk deploy --all`.
#
#   scripts/deploy_frontend.sh
#
# config.json holds the region, user pool id, and app client id. None of them are secrets.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REGION="us-east-1"
export AWS_REGION="$REGION" AWS_DEFAULT_REGION="$REGION"

output() { # stack key
  aws cloudformation describe-stacks --stack-name "$1" \
    --query "Stacks[0].Outputs[?OutputKey=='$2'].OutputValue" --output text
}

POOL_ID="$(output InsideSalesCopilot-Auth UserPoolId)"
CLIENT_ID="$(output InsideSalesCopilot-Auth UserPoolClientId)"
BUCKET="$(output InsideSalesCopilot-Web BucketName)"
DIST_ID="$(output InsideSalesCopilot-Web DistributionId)"
SITE_URL="$(output InsideSalesCopilot-Web SiteUrl)"
for v in POOL_ID CLIENT_ID BUCKET DIST_ID SITE_URL; do
  [ -n "${!v}" ] && [ "${!v}" != "None" ] || { echo "Missing stack output for $v. Did cdk deploy finish?" >&2; exit 1; }
done

cd "$ROOT/frontend"
unset VITE_USE_MOCKS            # production: real API and Cognito, never the mock
npm run build:prod

cat > dist/config.json <<EOF
{ "region": "$REGION", "userPoolId": "$POOL_ID", "userPoolClientId": "$CLIENT_ID" }
EOF

# Hashed assets can be cached for a year; index.html and config.json must always be fresh.
aws s3 sync dist "s3://$BUCKET" --delete --exclude index.html --exclude config.json \
  --cache-control "public,max-age=31536000,immutable" --only-show-errors
aws s3 cp dist/index.html "s3://$BUCKET/index.html" --cache-control "no-cache" --content-type "text/html" --only-show-errors
aws s3 cp dist/config.json "s3://$BUCKET/config.json" --cache-control "no-cache" --content-type "application/json" --only-show-errors

INVALIDATION="$(aws cloudfront create-invalidation --distribution-id "$DIST_ID" --paths '/*' --query 'Invalidation.Id' --output text)"
aws cloudfront wait invalidation-completed --distribution-id "$DIST_ID" --id "$INVALIDATION"

echo "Frontend deployed: $SITE_URL"
