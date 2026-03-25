Successfully initialized codebase:
```
{project_path}
├── backend/
│   ├── README.md
│   ├── requirements.txt
│   └── src/
│       ├── __init__.py
│       ├── main.py
│       └── tests/
│           └── __init__.py
└── frontend
    ├── README.md
    ├── bun.lock
    ├── components.json
    ├── eslint.config.js
    ├── index.html
    ├── package.json
    ├── public/
    │   └── _redirects
    ├── src/
    │   ├── App.tsx
    │   ├── components/
    │   │   └── ui
    │   │       └── button.tsx
    │   ├── index.css
    │   ├── lib/
    │   │   └── utils.ts
    │   ├── main.tsx
    │   └── vite-env.d.ts
    ├── tsconfig.app.json
    ├── tsconfig.json
    ├── tsconfig.node.json
    └── vite.config.ts
```

Installed dependencies:
- Frontend: `bun install`
- Backend: `pip install -r requirements.txt`
```
fastapi
uvicorn
sqlalchemy
python-dotenv
pydantic
pydantic-settings
pytest
pytest-asyncio
httpx
openai
bcrypt
python-jose[cryptography]
python-multipart
cryptography
requests
```

Live dev servers (auto-started, ports may shift to nearest available): Backend (FastAPI + uvicorn) defaults to http://localhost:8000 via session `backend`; Frontend (Vite) defaults to http://localhost:5173 via session `frontend`.

Utilize the Shadcn UI library for the frontend. Add components with `bunx shadcn@latest add -y -o`. Import components with `@/` alias. Note, 'toast' is deprecated, use 'sonner' instead.
