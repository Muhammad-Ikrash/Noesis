# Noesis Frontend

Angular 22 (standalone components, signals, zoneless) client for the Noesis backend.

```bash
npm install
npm start          # http://localhost:4200, proxies /api to http://127.0.0.1:8000 (proxy.conf.json)
npm run build
```

Start the backend first (`Backend/README.md`).

## Structure

```
src/app/
├── core/       api models + base URL, services (documents, conversations, quiz, settings, toast, theme),
│               auth seam (auth.service/interceptor/guard), HTTP error handling
├── shared/     design-system pieces: icon, toast host, confirm dialog, PDF viewer (pdf.js), rich text
└── features/   library · workspace (viewer + chat) · reader · quiz (list, runner, result)
src/styles/     tokens (colour, type, spacing; light + dark), base, shared component classes
```

## Auth (not enabled)

The backend is local-only. `AuthService` reports signed-in while `AUTH_ENABLED = false`; the interceptor attaches a
bearer token once one exists, and `authGuard` already wraps every route. To add auth: implement login against the
backend, set `AUTH_ENABLED = true`, and add the reserved `/login` route in `app.routes.ts`.
