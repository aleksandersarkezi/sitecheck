#!/usr/bin/env bash
# Roll out a specific image tag on the server, roll back if it's unhealthy.
#
#   bash ~/sitecheck/deploy.sh sha-1a2b3c4     # called by GitHub Actions
#   bash ~/sitecheck/deploy.sh sha-0f9e8d7     # manual rollback to an older build
set -euo pipefail

NEW_TAG="${1:?usage: deploy.sh <image-tag>}"
if [[ ! "$NEW_TAG" =~ ^[A-Za-z0-9._-]{1,128}$ ]]; then
  echo "invalid tag: $NEW_TAG" >&2
  exit 2
fi

cd "$(dirname "$0")"

if [[ ! -f .env ]]; then
  echo ".env missing in $(pwd). Copy .env.example to .env and fill it in first." >&2
  exit 1
fi
if [[ ! -f sites.txt ]]; then
  echo "sites.txt missing, creating an empty watchlist"
  echo "# one host per line" > sites.txt
fi

OLD_TAG="$(grep -E '^IMAGE_TAG=' .env | cut -d= -f2- || true)"
OLD_TAG="${OLD_TAG:-latest}"

set_tag() {
  if grep -qE '^IMAGE_TAG=' .env; then
    sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=$1/" .env
  else
    echo "IMAGE_TAG=$1" >> .env
  fi
}

wait_healthy() {
  local id status
  for _ in $(seq 1 30); do
    id="$(docker compose ps -q app)"
    status="$(docker inspect -f '{{.State.Health.Status}}' "$id" 2>/dev/null || echo starting)"
    if [[ "$status" == "healthy" ]]; then
      return 0
    fi
    sleep 2
  done
  return 1
}

# The Caddyfile is bind-mounted as a single file. rsync replaces it with a new
# file, which the running container doesn't see, so Caddy is recreated
# whenever the file's content actually changed.
reload_caddy_if_changed() {
  local new old
  new="$(sha256sum Caddyfile | cut -d' ' -f1)"
  old="$(cat .caddyfile.sha256 2>/dev/null || true)"
  if [[ "$new" != "$old" ]]; then
    echo "Caddyfile changed, recreating caddy"
    docker compose up -d --force-recreate --no-deps caddy
    echo "$new" > .caddyfile.sha256
  fi
}

# Writes "Deployed from commit X on DATE" into the home page footer, between
# the <!-- deploy --> markers. Visitors can see the page really is built from
# a specific commit and click through to it.
REPO_URL="${REPO_URL:-https://github.com/aleksandersarkezi/sitecheck}"
stamp_site() {
  local tag="$1" sha when
  [[ -f site/index.html ]] || return 0
  [[ "$tag" =~ ^sha-([0-9a-f]{7,40})$ ]] || return 0
  sha="${BASH_REMATCH[1]}"
  when="$(date -u '+%-d %b %Y, %H:%M UTC')"
  sed -i -E "s#<!-- deploy -->.*<!-- /deploy -->#<!-- deploy -->Deployed from commit <a href=\"${REPO_URL}/commit/${sha}\">${sha}</a> on ${when}.<!-- /deploy -->#" site/index.html
}

mkdir -p site

echo "deploying $NEW_TAG (current: $OLD_TAG)"
set_tag "$NEW_TAG"
docker compose pull --quiet
docker compose up -d --remove-orphans

if wait_healthy; then
  echo "app is healthy on $NEW_TAG"
  stamp_site "$NEW_TAG"
  reload_caddy_if_changed
  # Keep the disk from filling up with old images.
  docker image prune -f --filter "until=168h" > /dev/null
  exit 0
fi

echo "app did not become healthy, rolling back to $OLD_TAG" >&2
docker compose logs --tail=50 app >&2 || true
set_tag "$OLD_TAG"
docker compose up -d --remove-orphans
if wait_healthy; then
  stamp_site "$OLD_TAG"
  echo "rollback to $OLD_TAG OK" >&2
else
  echo "rollback to $OLD_TAG is unhealthy too, check the server" >&2
fi
exit 1
