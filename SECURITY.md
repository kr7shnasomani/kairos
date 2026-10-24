# Security Policy

## Reporting a vulnerability

Please report security issues privately through GitHub: open the repository's **Security** tab and
choose **Report a vulnerability**. Do not open a public issue, pull request or discussion for a
security problem.

Include what you found, the steps to reproduce it, and the impact you expect. You should get an
acknowledgement within 3 working days and a plan or fix within 14 days. If the report is valid, you
will be credited in the advisory unless you ask not to be.

## Supported versions

Only the `main` branch and the live deployment built from it receive security fixes.

## Scope

In scope: the code in this repository and the live demo built from it. Out of scope: the third-party
services Kairos calls (Supabase, Neo4j Aura, Qdrant Cloud, NVIDIA NIM, Nebius Token Factory, Groq,
Jina), denial-of-service by volume, and findings that need a compromised account or device.

## How dependencies are protected

The supply-chain guards (pinned and hash-verified dependencies, blocked install scripts, a 7-day
release-age rule, pinned base images and CI actions, and the audits that gate CI) are described in
[README § Supply-Chain Security](README.md#supply-chain-security).
