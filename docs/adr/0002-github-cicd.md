# ADR 0002: GitHub OIDC instead of access keys

- Status: accepted
- Date: 2026-10-30

## Context
GitHub Actions needs to deploy to AWS. The usual way is to save an AWS access key in GitHub.
Access keys never expire, so if one leaks, anyone can use it until someone notices.

## Decision
GitHub signs in to AWS with OIDC. Each run gets a token from GitHub, and AWS swaps it for
credentials that last at most 1 hour.
The role only trusts the main branch of this repo, matched by its owner and repo IDs.
The role can only pass the work to the CDK bootstrap roles. It has no other permissions.

## Alternatives considered
- Access keys saved as GitHub secrets: long-lived, and they have to be rotated by hand.
- Deploy only from my laptop: works, but not repeatable and not how teams work.

## Consequences
- No AWS keys are stored anywhere.
- Repos created after July 2026 send a subject with owner and repo IDs
  (repo:owner@id/name@id). The first deploy failed until the trust rule matched this format.
- If the repo is deleted and re-created with the same name, it gets new IDs and can't use the role.
- Deploys are started by hand from the Actions tab, so nothing deploys or costs money by surprise.