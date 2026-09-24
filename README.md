# Northstar Data Analyst

Northstar is a CSV-based natural-language data analysis application. Users create a private workspace, upload one or more CSV files, ask questions about the data, and receive:

- A human-readable explanation
- A verified SQL result executed with DuckDB
- Charts for supported analytical questions
- A full summary report for overview questions
- Dataset quality and schema information
- Conversation history

The application is local-first for storage and computation. The optional Groq integration is used for intent classification, SQL generation, and answer refinement. The backend always validates generated SQL before it is executed.

## Technology stack

### Frontend

- React 19
- TypeScript
- Vite
- Recharts
- Lucide React
- Fetch API with cookie credentials

The frontend is in [`frontend/`](./frontend/).

### Backend

- Python 3.14-compatible environment
- FastAPI
- Uvicorn
- Pydantic Settings
- SQLAlchemy
- SQLite by default
- pandas for CSV loading, profiling, deterministic analysis, and data preparation
- DuckDB for safe, read-only SQL execution against in-memory DataFrames
- python-multipart for multi-file uploads
- Authlib/httpx for Google OAuth
- OpenAI-compatible client pointed at the Groq API

The backend is in [`backend/`](./backend/).

### AI model

The default model is configured with:

```text
GROQ_MODEL=openai/gpt-oss-120b
```

There is no local model file in this repository. When `GROQ_API_KEY` is configured, the backend calls Groq through its OpenAI-compatible API. If Groq is unavailable, deterministic pandas analysis and safe fallback SQL keep the core flow usable.

## Architecture

## Architecture

![Northstar Data Analyst Architecture](docs/northstar_architecture.png)

### Architecture Flow

```text
User
 ↓
React + Vite
 ↓
FastAPI
 ↓
Schema + Question
 ↓
Groq LLM
 ↓
SQL Generation
 ↓
SQL Validation
 ↓
DuckDB
 ↓
Verified Result
 ├──→ LLM Explanation
 └──→ Chart Generator
 ↓
React Dashboard
## Analysis flow

For a normal analytical question:

```text
1. User uploads one or more CSV files.
2. Backend profiles each file with pandas.
3. User asks a natural-language question.
4. Backend loads and combines the selected datasets.
5. Backend checks whether the question is related to the dataset.
6. Dataset schema and question are used for intent classification.
7. A deterministic analysis plan creates a safe fallback SQL shape and evidence.
8. Groq may generate SQL from the question, intent, schema, and fallback shape.
9. SQL validation allows only one read-only SELECT/WITH statement against dataset.
10. DuckDB executes the validated SQL over the uploaded DataFrame.
11. The verified result is sent to Groq for a concise explanation.
12. React renders the explanation, chart, verified rows, SQL, and metadata.
```

If the Groq key is missing or an LLM request fails, the deterministic fallback remains available. LLM-generated SQL is never executed before validation.

## Summary report flow

Questions such as:

```text
Give me a complete summary of this dataset
```

produce a structured report containing:

- Row and column counts
- Duplicate row count
- Missing cell count
- Per-column schema and null statistics
- Unique values and sample values
- Numeric count, mean, median, minimum, maximum, and standard deviation
- Top categorical values and frequencies
- The first 10 sample rows
- A read-only DuckDB row-count verification query

Missing values are serialized as JSON `null`, not pandas `NaN`, so the API response remains valid JSON.

## Multi-file behavior

The upload input supports selecting multiple CSV files in one operation.

- Files with matching schemas are concatenated.
- Files with common non-numeric columns can be merged on those common columns.
- Other incompatible files are concatenated with missing columns filled as null.
- The UI supports selecting all uploaded files or analyzing one dataset.
- Valid files in a mixed upload are retained even if another file fails validation.

## Project structure

```text
.
├── backend/
│   ├── app/
│   │   ├── api/routes.py          # HTTP routes and upload/question handling
│   │   ├── auth.py                # Session user lookup
│   │   ├── config.py              # Environment-backed settings
│   │   ├── db.py                  # SQLAlchemy models and SQLite setup
│   │   ├── main.py                # FastAPI application, middleware, startup
│   │   └── services/
│   │       ├── analysis.py        # Relevance, analysis, summary, orchestration
│   │       ├── anomalies.py       # IQR anomaly detection
│   │       ├── intent.py          # Intent model and fallback classification
│   │       ├── llm.py             # Groq intent, SQL, and answer calls
│   │       ├── profiling.py       # CSV schema and quality profiling
│   │       └── query.py           # SQL safety validation and DuckDB execution
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx                # Main workspace UI and result rendering
│   │   ├── api.ts                 # Backend API client
│   │   └── types.ts               # Frontend API types
│   └── package.json
└── .env.example
```

## Setup

### Prerequisites

- Python 3.11+ recommended
- Node.js 20+ recommended
- npm
- Google OAuth credentials if authentication is required
- Groq API key if LLM-powered classification, SQL generation, and explanation are required

### 1. Configure the backend

From PowerShell:

```powershell
Set-Location "E:\BACKUP\Digital Back Office"
Copy-Item ".env.example" "backend\.env"
```

Edit [`backend/.env`](./backend/.env) and set at least:

```dotenv
APP_ENV=development
FRONTEND_URL=http://localhost:5173
BACKEND_URL=http://localhost:8000
SESSION_SECRET=replace-with-a-long-random-value
DATABASE_URL=sqlite:///./analyst.db
DATA_DIR=./data
GROQ_API_KEY=your-groq-api-key
GROQ_MODEL=openai/gpt-oss-120b
```

For Google login, also set:

```dotenv
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/auth/callback
```

The backend loads `.env` relative to its working directory, so start Uvicorn from `backend/`.

### 2. Install backend dependencies

```powershell
Set-Location "E:\BACKUP\Digital Back Office"
& ".venv\Scripts\python.exe" -m pip install -r "backend\requirements.txt"
```

If the root `.venv` does not exist, create one:

```powershell
Set-Location "E:\BACKUP\Digital Back Office"
py -m venv .venv
& ".venv\Scripts\python.exe" -m pip install -r "backend\requirements.txt"
```

### 3. Start the backend

```powershell
Set-Location "E:\BACKUP\Digital Back Office\backend"
& "..\.venv\Scripts\python.exe" -m uvicorn app.main:app --reload --port 8000
```

Verify it with:

```text
http://localhost:8000/health
```

Expected response:

```json
{
  "status": "ok",
  "service": "northstar-api"
}
```

### 4. Install and start the frontend

In a second PowerShell window:

```powershell
Set-Location "E:\BACKUP\Digital Back Office\frontend"
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

To use a different backend URL, create `frontend/.env.local`:

```dotenv
VITE_API_URL=http://localhost:8000/api
```

## Main API endpoints

All application routes are prefixed with `/api`.

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Backend health check |
| `GET` | `/api/auth/me` | Current session |
| `GET` | `/api/projects` | List workspaces |
| `POST` | `/api/projects` | Create a workspace |
| `GET` | `/api/projects/{id}` | Workspace and dataset metadata |
| `POST` | `/api/projects/{id}/datasets` | Upload one or more CSV files |
| `POST` | `/api/projects/{id}/datasets/{dataset_id}/ask` | Analyze a question |
| `GET` | `/api/projects/{id}/datasets/{dataset_id}/rows` | Paginated dataset rows |
| `GET` | `/api/projects/{id}/messages` | Conversation history |

## Security and validation

- Google OAuth state is checked before accepting callbacks.
- Session cookies are managed by Starlette middleware.
- Uploaded files must be CSV files and are size-limited.
- SQL must be a single `SELECT` or `WITH` statement.
- SQL write and extension operations are rejected.
- SQL may reference only the registered `dataset` table.
- DuckDB runs in memory against the uploaded pandas DataFrame.
- LLM responses are treated as untrusted input and are validated before execution.

## Verification commands

Backend tests:

```powershell
Set-Location "E:\BACKUP\Digital Back Office\backend"
& "..\.venv\Scripts\python.exe" -m pytest
```

Frontend lint and build:

```powershell
Set-Location "E:\BACKUP\Digital Back Office\frontend"
npm run lint
npm run build
```

## Current storage model

The default deployment uses SQLite, not PostgreSQL or Redis:

- SQLite stores users, projects, dataset metadata, and messages.
- Uploaded CSV files are stored under `DATA_DIR`.
- pandas and DuckDB process analytical data in memory.
- Redis and PostgreSQL are not required by the current implementation.
