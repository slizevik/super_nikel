---
applyTo: "frontend/**/*.{ts,tsx,css,html}"
---

# Frontend rules

- The active UI is React with TypeScript under `frontend/`; preserve its current API URL and job-polling contracts.
- Represent loading, failed, and non-terminal `awaiting_persistence` states distinctly. Do not present extraction completion as graph persistence success.
- Keep API response types aligned with FastAPI response schemas and update relevant UI behavior when contracts change.
- Do not place secrets in client code. Keep external service credentials on the backend.
- Run `npm run build` from `frontend/` after frontend changes.
