# CI/CD setup

The workflows implement the backend delivery path:

`PR → lint/format → unit tests → PostgreSQL/Redis/Qdrant integration → security scan → merge → image build → Trivy → GHCR → staging smoke test → production approval → production smoke test`.

## One-time GitHub setup

1. In **Settings → Actions → General**, allow GitHub Actions to create and write packages.
2. Protect `main` and require the `Backend CI` checks before merge.
3. Create a `staging` environment and add these secrets:
   - `STAGING_HOST`
   - `STAGING_USER`
   - `STAGING_SSH_KEY`
   - `STAGING_DEPLOY_PATH`
   - `STAGING_HEALTH_URL`
4. Create a `production` environment, add required reviewers, then add:
   - `PRODUCTION_HOST`
   - `PRODUCTION_USER`
   - `PRODUCTION_SSH_KEY`
   - `PRODUCTION_DEPLOY_PATH`
   - `PRODUCTION_HEALTH_URL`

Each deployment server must contain the repository's `docker-compose.yml` and a
production `.env`. GitHub Actions sets `ATLAS_IMAGE` to the immutable GHCR SHA
tag, pulls it, and restarts only `api`, `celery_worker`, and `celery_beat`.

The production environment's required-reviewer rule is the manual approval
gate; it is intentionally configured in GitHub, not hard-coded in a workflow.
