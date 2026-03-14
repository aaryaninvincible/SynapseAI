# Cloud Run (Backend)

Build and deploy backend service:

```bash
gcloud builds submit --tag gcr.io/<PROJECT_ID>/screensense-agent ./apps/agent
gcloud run deploy screensense-agent \
  --image gcr.io/<PROJECT_ID>/screensense-agent \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars GOOGLE_API_KEY=<KEY>,ALLOWED_ORIGINS=*
```

## One-Command Script (PowerShell)

```powershell
./infra/cloudrun/deploy.ps1 `
  -ProjectId "<PROJECT_ID>" `
  -Region "us-central1" `
  -AllowedOrigins "*" `
  -GcpProjectId "<PROJECT_ID>" `
  -GcsBucketName "<OPTIONAL_BUCKET>"
```

Recommended after deploy:

1. Set `GOOGLE_API_KEY` as a Cloud Run secret env var.
2. Update frontend `VITE_AGENT_BASE_URL` to the Cloud Run URL.
3. Verify `/health` and websocket `/ws/{session_id}` from browser.
