# AI Knowledge Base MVP

A multi-tenant AI retrieval platform where organizations can ingest public documentation (PDFs and web pages) and query them through a premium web interface with streaming responses and source citations.

## Architecture

```
┌──────────────────┐     ┌──────────────────────────────────────┐
│   React + Vite   │────▶│           FastAPI Backend            │
│  (Glassmorphism) │ SSE │                                      │
│   Port: 3000     │◀────│   Port: 8000                         │
└──────────────────┘     │                                      │
                         │  ┌────────────┐  ┌────────────────┐  │
                         │  │ ChromaDB   │  │ Delta Lake     │  │
                         │  │ (Vectors)  │  │ (Metadata)     │  │
                         │  └────────────┘  └────────────────┘  │
                         └──────────────────────────────────────┘
```

### Key Design Decisions
- **Pluggable Interfaces**: Abstract base classes for vector store and metadata store allow swapping local (ChromaDB + Delta Lake) to Databricks in production
- **Multi-Tenant Isolation**: All data is partitioned by `organization_id`
- **SSE Streaming**: Chat responses stream token-by-token via Server-Sent Events
- **RAG Pipeline**: Question → Embed → Vector Search → Context Assembly → LLM Stream

## Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+
- An OpenAI API key

### 1. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export OPENAI_API_KEY="your-openai-api-key"

# Start the server
uvicorn app.main:app --reload --port 8000
```

### 2. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start dev server (proxies API to backend)
npm run dev
```

### 3. Access the App
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

### Demo Credentials
| Username   | Password  | Organization |
|-----------|-----------|-------------|
| `admin`   | `admin123`| `demo_org`  |
| `uba_user`| `uba123`  | `uba`       |

## Docker Deployment

```bash
# Set your OpenAI API key
export OPENAI_API_KEY="your-key"

# Build and run
docker-compose up --build
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/auth/token` | Login and get JWT token |
| `POST` | `/api/v1/ingestion/upload` | Upload and index a PDF |
| `POST` | `/api/v1/ingestion/url` | Ingest a web page by URL |
| `GET`  | `/api/v1/ingestion/documents?org_id=X` | List org documents |
| `POST` | `/api/v1/chat` | Stream RAG chat response (SSE) |

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key (required) | — |
| `ENVIRONMENT` | `DEV` or `PROD` | `DEV` |
| `JWT_SECRET_KEY` | Secret for JWT signing | dev default |
| `VECTOR_PROVIDER` | `chroma` or `databricks` | `chroma` |
| `METADATA_PROVIDER` | `delta_local` or `databricks` | `delta_local` |

## Tech Stack

**Backend**: FastAPI, ChromaDB, Delta Lake (python-deltalake), OpenAI, pypdf, BeautifulSoup4  
**Frontend**: React, Vite, Vanilla CSS (Glassmorphism)  
**Infra**: Docker, Docker Compose
