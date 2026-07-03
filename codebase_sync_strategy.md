# Codebase Sync Strategy: GitHub & Databricks Integration

This guide outlines how to sync your codebase between your local development environment (where you can collaborate with me) and your Databricks workspace. It addresses your questions on code sync, hosting, and branch management.

---

## 1. Unified Codebase vs. Separate Branches

> [!IMPORTANT]
> **Recommendation: Keep a Single Branch and Use Configurations**
> You **do not need separate branches** for Databricks and other platforms. Because we built the storage layer to be pluggable, the exact same code runs in both places:
> - **Local / Google VM (Local Mode)**: Set `VECTOR_PROVIDER=chroma` and `METADATA_PROVIDER=delta_local` in your `.env`.
> - **Databricks Environment**: Set `VECTOR_PROVIDER=databricks` and `METADATA_PROVIDER=databricks` in your environment.
>
> Maintaining separate branches introduces major merge conflict overhead and makes it difficult to transfer logic improvements between environments. Keeping a single branch powered by different `.env` files is the standard **12-Factor App** architecture.

---

## 2. GitHub Sync Workflow (Recommended)

To run the codebase on Databricks while continuing to pair program with me locally, you should use **Databricks Git folders** linked to a shared GitHub repository.

```
┌────────────────────────┐          ┌──────────────────────┐          ┌────────────────────────┐
│ Local Workspace (IDE)  │  Push    │  GitHub Repository   │  Pull    │  Databricks Workspace  │
│ - Pair program with AI ├─────────▶│                      ├─────────▶│ - Run Databricks App   │
│ - Run local chroma/RAG │          │ - Single main branch │          │ - Connect to Serverless│
└────────────────────────┘          └──────────────────────┘          └────────────────────────┘
```

### Steps to Set Up:

1. **Create a Private GitHub Repository**:
   - Push your current local workspace folder (`BankGPT`) to a private GitHub repository.
2. **Configure Git Integration in Databricks**:
   - In your Databricks workspace, click on your **User Profile** (top-right) → **User Settings**.
   - Go to **Linked accounts** / **Git integration**.
   - Select **GitHub** and enter your GitHub Personal Access Token (PAT) with `repo` scopes.
3. **Create a Git Folder in Databricks**:
   - In the sidebar, click on **Workspace** → **Repos** (or **Git folders**).
   - Click **Add Repo** / **New Git folder**.
   - Paste your GitHub repository URL.
4. **Develop and Sync**:
   - **Local**: We build code, run local unit tests, and check in changes to GitHub.
   - **Databricks**: In the Databricks Git folder interface, simply click the **Pull** button (or use the Databricks Git CLI) to pull down the changes. The Databricks workspace immediately updates with the new code files.

---

## 3. Alternative: Deploying via Databricks Asset Bundles (DABs)

If you want an automated deployment experience (CI/CD) instead of clicking "Pull" manually:

- You can configure a **GitHub Action** that triggers on a push to `main`.
- The action uses the **Databricks CLI** to bundle and upload your FastAPI backend/frontend code as a **Databricks App** or copy it into workspace directories.
- This represents a production-grade CI/CD pipeline.

---

## Next Steps

1. Initialise git in your local project folder if you haven't already:
   ```bash
   git init
   git add .
   git commit -m "initial commit: local RAG + Databricks & MCP integration"
   ```
2. Push it to a GitHub repository, and connect it to your Databricks Workspace Git Folders.
