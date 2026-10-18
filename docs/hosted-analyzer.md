# Hosted analyzer deployment

The hosted service is `hosted_app.py`, a single FastAPI process suitable for
Railway, Render, or a similar small worker service. `Procfile` and
`render.yaml` provide the service command and environment-variable template.
The deployment is intentionally not committed with provider credentials.

## Required environment variables

- `FALKORDB_HOST`, `FALKORDB_PORT`, `FALKORDB_USERNAME`, `FALKORDB_PASSWORD`, and
  `FALKORDB_SSL`: FalkorDB Cloud connection settings.
- `OPENROUTER_API_KEY`: server-side only, and only needed when
  `IMPACT_HOSTED_LLM=true`.

## Limits and operations

- `IMPACT_MAX_REPOSITORY_BYTES` defaults to 250 MB.
- `IMPACT_MAX_PYTHON_FILES` defaults to 1,200.
- `IMPACT_MAX_FILE_BYTES` defaults to 2 MB.
- `IMPACT_MAX_ACTIVE_JOBS` defaults to 2.
- `IMPACT_RATE_LIMIT_SECONDS` defaults to 30 seconds per client.
- `IMPACT_RESULT_TTL_SECONDS` defaults to one hour.

The service accepts only `https://github.com/OWNER/REPO/pull/NUMBER`, fetches the
exact public PR head, and uses a unique graph name per job. It parses Python ASTs
and does not run repository code, tests, custom commands, or package installers.
The worker deletes its graph after rendering and removes expired result files.
Hosted reports label graph paths as possible impact. Test results are absent
because hosted analysis never runs tests; the local CLI remains the trusted-test
workflow.

## Final provider action

Create a service from this repository, add the FalkorDB settings as provider
secrets, deploy, and copy the assigned HTTPS URL into the `Hosted analyzer URL`
line in `README.md`. Verify a public PR URL, a malformed URL, a rate-limit
response, a completed shareable result URL, and the Markdown download before
announcing the endpoint.
