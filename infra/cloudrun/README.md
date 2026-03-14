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

