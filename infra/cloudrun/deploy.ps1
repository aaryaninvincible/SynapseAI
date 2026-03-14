param(
  [Parameter(Mandatory = $true)]
  [string]$ProjectId,
  [string]$Region = "us-central1",
  [string]$Service = "screensense-agent",
  [string]$Image = "screensense-agent",
  [string]$GeminiLiveModel = "gemini-2.0-flash-live-001",
  [string]$GeminiFallbackModel = "gemini-2.5-flash",
  [string]$AllowedOrigins = "*",
  [string]$GcpProjectId = "",
  [string]$GcsBucketName = ""
)

$ErrorActionPreference = "Stop"

gcloud config set project $ProjectId | Out-Null
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com

$imageUri = "$Region-docker.pkg.dev/$ProjectId/screensense/$Image:latest"

gcloud artifacts repositories create screensense `
  --repository-format=docker `
  --location=$Region `
  --description="ScreenSense images" `
  --project=$ProjectId 2>$null

gcloud builds submit ./apps/agent --tag $imageUri --project=$ProjectId

$envVars = @(
  "ALLOWED_ORIGINS=$AllowedOrigins",
  "GEMINI_LIVE_MODEL=$GeminiLiveModel",
  "GEMINI_FALLBACK_MODEL=$GeminiFallbackModel",
  "GCP_PROJECT_ID=$GcpProjectId",
  "GCS_BUCKET_NAME=$GcsBucketName"
) -join ","

gcloud run deploy $Service `
  --image $imageUri `
  --region $Region `
  --platform managed `
  --allow-unauthenticated `
  --set-env-vars $envVars `
  --project $ProjectId

Write-Host ""
Write-Host "Deployed service URL:"
gcloud run services describe $Service --region $Region --format="value(status.url)" --project=$ProjectId

