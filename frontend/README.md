# AttendFlow frontend

Run the FastAPI backend at `http://localhost:8000`, then run:

```bash
npm ci
npm run dev
```

Use Node 20.19+ or Node 22.13+. CI runs on Node 24. Open
`http://localhost:5173/dev` to investigate Amit's P1 and send the question.
Open `http://localhost:5173/` for Amit's inbox. The demo actors are defined
in `src/actors.ts`. The API URL can be overridden with `VITE_API_BASE_URL`.

Run `npm test`, `npm run typecheck`, or `npm run build` from this directory.
With the backend dependencies installed, `npm run api:generate` updates the
generated types from FastAPI's OpenAPI schema and `npm run api:check` checks
for drift. Set `ATTENDFLOW_PYTHON` to a Python interpreter path relative to
the repo root if `uv` is unavailable on PATH.
