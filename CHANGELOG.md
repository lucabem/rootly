# Changelog

## Unreleased

### 2026-05-06
- **docs: add contributing guide and MIT license** — Added CONTRIBUTING.md with setup instructions, project layout, development workflows, and commit conventions; added MIT LICENSE.md to establish open-source governance.

### 2026-05-05
- **feat(auth): add JWT authentication and role-based permissions** — Added JWT authentication (HS256 and RS256/JWKS) with support for dev mode, role-based access control via DynamoDB, and Azure AD SSO for frontend. Includes new /api/me endpoint and permission checks on API routes.

### 2026-05-05
- **refactor(hooks): defer changelog updates to post-commit hook** — Moved changelog file writing to post-commit hook to ensure clean staging area during prepare-commit-msg phase, fixing issues with changelog generation workflow.

### 2026-05-05
- **style: add Rootly logo to header and empty state** — Added Rootly logo image to application header and empty state UI for improved branding and visual identity.

### 2026-05-05
- **refactor: decompose GraphView and enhance RAG with semantic search** — Refactored GraphView into modular components (controls, context menu, layout), added semantic search with Athena integration, improved backend caching of filter terms and datasets, increased proxy timeout to 300s, and enhanced UI with markdown tables, code copy buttons, and loading suggestions.

### 2026-05-05
- **feat(rag): add Claude commit hooks and improve knowledge chunking** — Added git hooks that auto-generate conventional commit messages and changelog entries using Claude Haiku; improved knowledge document splitting to handle large tables and long sections intelligently.
