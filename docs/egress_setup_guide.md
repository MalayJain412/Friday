# Complete Egress Setup Guide for LiveKit Voice Bot

Based on the code analysis from `cagent.py`, egress scripts, and related files, here's the complete setup guide for implementing audio recording and egress in a new LiveKit voice bot:

## **1. Dependencies Required**

Add these to your `requirements.txt`:

```txt
# Core LiveKit
livekit==1.0.12
livekit-agents==1.2.14
livekit-api==1.0.5

# Azure Storage (for cloud storage)
azure-storage-blob==12.19.0
azure-identity==1.15.0

# Web Framework for Egress Manager
fastapi==0.104.1
uvicorn==0.24.0
pydantic==2.5.0
python-jose[cryptography]==3.3.0

# HTTP Client
requests==2.32.5

# Environment Management
python-dotenv==1.1.1
```

## **2. Core Files to Create**

### **A. `egress_manager.py`** - Main egress management system
```python
import os
import asyncio
import logging
from typing import Optional, Dict, Any
from datetime import datetime
import json

from livekit import api as lkapi
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import ResourceExistsError

class EgressManager:
    """Manages LiveKit egress recording operations"""

    def __init__(self):
        self.livekit_api: Optional[lkapi.LiveKitAPI] = None
        self.azure_client: Optional[BlobServiceClient] = None
        self.recordings_dir = "recordings"
        os.makedirs(self.recordings_dir, exist_ok=True)

    async def initialize(self):
        """Initialize LiveKit API and Azure Storage connections"""
        try:
            # LiveKit API setup
            livekit_url = os.getenv("LIVEKIT_URL")
            api_key = os.getenv("LIVEKIT_API_KEY")
            api_secret = os.getenv("LIVEKIT_API_SECRET")

            if not all([livekit_url, api_key, api_secret]):
                raise ValueError("Missing LiveKit environment variables")

            # Convert ws:// to http:// for API calls
            http_host = livekit_url
            if http_host.startswith("ws://"):
                http_host = "http://" + http_host[len("ws://"):]
            elif http_host.startswith("wss://"):
                http_host = "https://" + http_host[len("wss://"):]

            self.livekit_api = lkapi.LiveKitAPI(http_host, api_key, api_secret)

            # Azure Storage setup (optional)
            azure_connection = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
            if azure_connection:
                self.azure_client = BlobServiceClient.from_connection_string(azure_connection)
                await self._ensure_container_exists()

            logging.info("EgressManager initialized successfully")

        except Exception as e:
            logging.error(f"Failed to initialize EgressManager: {e}")
            raise

    async def _ensure_container_exists(self):
        """Ensure Azure container exists"""
        if not self.azure_client:
            return

        container_name = os.getenv("AZURE_CONTAINER_NAME", "livekit-recordings")
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, self.azure_client.create_container, container_name
            )
            logging.info(f"Created Azure container: {container_name}")
        except ResourceExistsError:
            logging.info(f"Azure container already exists: {container_name}")
        except Exception as e:
            logging.warning(f"Failed to create Azure container: {e}")

    async def start_recording(self, room_name: str, audio_only: bool = True) -> Optional[str]:
        """Start egress recording for a room"""
        if not self.livekit_api:
            logging.error("LiveKit API not initialized")
            return None

        try:
            # Generate unique filename
            timestamp = int(datetime.utcnow().timestamp())
            filename = f"{room_name}-{timestamp}.mp4"
            filepath = f"{self.recordings_dir}/{filename}"

            # Create file output
            file_output = lkapi.EncodedFileOutput(filepath=filepath)

            # Create egress request
            req = lkapi.RoomCompositeEgressRequest(
                room_name=room_name,
                audio_only=audio_only,
                file_outputs=[file_output]
            )

            # Start egress
            info = await self.livekit_api.egress.start_room_composite_egress(req)
            egress_id = info.egress_id

            logging.info(f"Recording started: egress_id={egress_id}, file={filepath}")

            # Store metadata
            await self._store_egress_metadata(egress_id, room_name, filepath)

            return egress_id

        except Exception as e:
            logging.error(f"Failed to start recording for room {room_name}: {e}")
            return None

    async def stop_recording(self, egress_id: str) -> bool:
        """Stop egress recording"""
        if not self.livekit_api:
            logging.error("LiveKit API not initialized")
            return False

        try:
            req = lkapi.StopEgressRequest(egress_id=egress_id)
            await self.livekit_api.egress.stop_egress(req)
            logging.info(f"Recording stopped: egress_id={egress_id}")
            return True
        except Exception as e:
            logging.error(f"Failed to stop recording {egress_id}: {e}")
            return False

    async def _store_egress_metadata(self, egress_id: str, room_name: str, filepath: str):
        """Store egress metadata for later retrieval"""
        metadata = {
            "egress_id": egress_id,
            "room_name": room_name,
            "filepath": filepath,
            "started_at": datetime.utcnow().isoformat(),
            "status": "recording"
        }

        metadata_file = f"{self.recordings_dir}/EG_{egress_id}.json"
        try:
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
            logging.info(f"Egress metadata stored: {metadata_file}")
        except Exception as e:
            logging.error(f"Failed to store egress metadata: {e}")

    async def upload_to_cloud(self, local_path: str, cloud_name: Optional[str] = None) -> Optional[str]:
        """Upload recording to cloud storage"""
        if not self.azure_client:
            logging.warning("Azure client not configured, skipping cloud upload")
            return None

        try:
            container_name = os.getenv("AZURE_CONTAINER_NAME", "livekit-recordings")
            blob_name = cloud_name or os.path.basename(local_path)

            blob_client = self.azure_client.get_blob_client(
                container=container_name, blob=blob_name
            )

            # Upload file
            with open(local_path, "rb") as data:
                await asyncio.get_event_loop().run_in_executor(
                    None, blob_client.upload_blob, data, True
                )

            cloud_url = f"https://{self.azure_client.account_name}.blob.core.windows.net/{container_name}/{blob_name}"
            logging.info(f"File uploaded to cloud: {cloud_url}")
            return cloud_url

        except Exception as e:
            logging.error(f"Failed to upload {local_path} to cloud: {e}")
            return None

    async def cleanup_old_recordings(self, days_old: int = 7):
        """Clean up old recording files"""
        try:
            cutoff_time = datetime.utcnow().timestamp() - (days_old * 24 * 60 * 60)

            for filename in os.listdir(self.recordings_dir):
                if not filename.endswith(('.mp4', '.wav', '.ogg')):
                    continue

                filepath = os.path.join(self.recordings_dir, filename)
                file_time = os.path.getmtime(filepath)

                if file_time < cutoff_time:
                    os.remove(filepath)
                    logging.info(f"Cleaned up old recording: {filename}")

        except Exception as e:
            logging.error(f"Failed to cleanup old recordings: {e}")

    async def close(self):
        """Close all connections"""
        if self.livekit_api:
            await self.livekit_api.aclose()
            logging.info("LiveKit API connection closed")

# Global instance
egress_manager = EgressManager()
```

### **B. `egress_api.py`** - REST API for egress management
```python
import os
import hmac
import hashlib
import json
from typing import Dict, Any
from datetime import datetime

from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

from egress_manager import egress_manager

app = FastAPI(title="LiveKit Egress Manager API")

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")

class StartRecordingRequest(BaseModel):
    room_name: str
    audio_only: bool = True

class StopRecordingRequest(BaseModel):
    egress_id: str

def verify_signature(raw: bytes, signature_header: str) -> bool:
    """Verify webhook signature"""
    if not WEBHOOK_SECRET:
        return True
    mac = hmac.new(WEBHOOK_SECRET.encode(), raw, digestmod=hashlib.sha256)
    expected = mac.hexdigest()
    return hmac.compare_digest(expected, signature_header)

@app.on_event("startup")
async def startup_event():
    """Initialize egress manager on startup"""
    await egress_manager.initialize()

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up on shutdown"""
    await egress_manager.close()

@app.post("/recording/start")
async def start_recording(request: StartRecordingRequest):
    """Start recording for a room"""
    egress_id = await egress_manager.start_recording(
        request.room_name,
        request.audio_only
    )

    if egress_id:
        return {"status": "success", "egress_id": egress_id}
    else:
        raise HTTPException(status_code=500, detail="Failed to start recording")

@app.post("/recording/stop")
async def stop_recording(request: StopRecordingRequest):
    """Stop recording"""
    success = await egress_manager.stop_recording(request.egress_id)

    if success:
        return {"status": "success"}
    else:
        raise HTTPException(status_code=500, detail="Failed to stop recording")

@app.post("/webhook")
async def webhook(request: Request, x_signature: str = Header(None)):
    """Handle LiveKit webhooks"""
    body = await request.body()
    if not verify_signature(body, x_signature or ""):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    event_type = payload.get("event") or payload.get("type")

    if event_type == "egress_completed":
        info = payload.get("info", {})
        egress_id = info.get("egress_id")

        # Update metadata file
        metadata_file = f"recordings/EG_{egress_id}.json"
        try:
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)

            metadata["status"] = "completed"
            metadata["completed_at"] = datetime.utcnow().isoformat()

            # Extract file information
            outputs = info.get("outputs", [])
            if outputs:
                metadata["filename"] = outputs[0].get("filename")

            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)

            # Optionally upload to cloud
            if os.getenv("AUTO_UPLOAD_TO_CLOUD", "false").lower() == "true":
                local_path = metadata.get("filepath")
                if local_path and os.path.exists(local_path):
                    cloud_url = await egress_manager.upload_to_cloud(local_path)
                    if cloud_url:
                        metadata["cloud_url"] = cloud_url
                        with open(metadata_file, 'w') as f:
                            json.dump(metadata, f, indent=2)

        except Exception as e:
            logging.error(f"Failed to process egress completion: {e}")

    return {"status": "ok"}

@app.get("/recordings")
async def list_recordings():
    """List all recordings"""
    try:
        recordings = []
        for filename in os.listdir("recordings"):
            if filename.endswith(".json"):
                with open(f"recordings/{filename}", 'r') as f:
                    metadata = json.load(f)
                    recordings.append(metadata)

        return {"recordings": recordings}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8081)
```

### **C. `azure_storage.py`** - Azure Storage utilities
```python
import os
import asyncio
import logging
from typing import Optional
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import ResourceExistsError

class AzureStorageManager:
    """Azure Blob Storage manager for recordings"""

    def __init__(self):
        self.connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        self.container_name = os.getenv("AZURE_CONTAINER_NAME", "livekit-recordings")
        self.client: Optional[BlobServiceClient] = None

        if self.connection_string:
            self.client = BlobServiceClient.from_connection_string(self.connection_string)

    async def ensure_container_exists(self):
        """Create container if it doesn't exist"""
        if not self.client:
            return

        try:
            await asyncio.get_event_loop().run_in_executor(
                None, self.client.create_container, self.container_name
            )
            logging.info(f"Created Azure container: {self.container_name}")
        except ResourceExistsError:
            pass  # Container already exists
        except Exception as e:
            logging.error(f"Failed to create Azure container: {e}")

    async def upload_file(self, local_path: str, blob_name: Optional[str] = None) -> Optional[str]:
        """Upload file to Azure Blob Storage"""
        if not self.client:
            logging.warning("Azure client not configured")
            return None

        try:
            blob_name = blob_name or os.path.basename(local_path)

            blob_client = self.client.get_blob_client(
                container=self.container_name, blob=blob_name
            )

            # Upload file
            with open(local_path, "rb") as data:
                await asyncio.get_event_loop().run_in_executor(
                    None, blob_client.upload_blob, data, True
                )

            # Generate URL
            url = f"https://{self.client.account_name}.blob.core.windows.net/{self.container_name}/{blob_name}"
            logging.info(f"File uploaded to Azure: {url}")
            return url

        except Exception as e:
            logging.error(f"Failed to upload {local_path} to Azure: {e}")
            return None

    async def download_file(self, blob_name: str, local_path: str) -> bool:
        """Download file from Azure Blob Storage"""
        if not self.client:
            return False

        try:
            blob_client = self.client.get_blob_client(
                container=self.container_name, blob=blob_name
            )

            with open(local_path, "wb") as download_file:
                download_stream = await asyncio.get_event_loop().run_in_executor(
                    None, blob_client.download_blob
                )
                download_file.write(download_stream.readall())

            logging.info(f"File downloaded from Azure: {blob_name} -> {local_path}")
            return True

        except Exception as e:
            logging.error(f"Failed to download {blob_name} from Azure: {e}")
            return False

    async def list_files(self, prefix: str = "") -> list:
        """List files in container"""
        if not self.client:
            return []

        try:
            container_client = self.client.get_container_client(self.container_name)
            blobs = await asyncio.get_event_loop().run_in_executor(
                None, lambda: list(container_client.list_blobs(name_starts_with=prefix))
            )

            return [blob.name for blob in blobs]

        except Exception as e:
            logging.error(f"Failed to list Azure files: {e}")
            return []

# Global instance
azure_manager = AzureStorageManager()
```

### **D. `recording_manager.py`** - Recording lifecycle management
```python
import os
import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from pathlib import Path

class RecordingManager:
    """Manages recording files and metadata"""

    def __init__(self, recordings_dir: str = "recordings"):
        self.recordings_dir = Path(recordings_dir)
        self.recordings_dir.mkdir(exist_ok=True)

    def store_metadata(self, egress_id: str, room_name: str, filepath: str,
                      caller_number: Optional[str] = None) -> bool:
        """Store recording metadata"""
        try:
            metadata = {
                "egress_id": egress_id,
                "room_name": room_name,
                "filepath": filepath,
                "filename": os.path.basename(filepath),
                "caller_number": caller_number,
                "started_at": datetime.utcnow().isoformat(),
                "status": "recording",
                "file_size": 0
            }

            metadata_file = self.recordings_dir / f"EG_{egress_id}.json"
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)

            logging.info(f"Recording metadata stored: {metadata_file}")
            return True

        except Exception as e:
            logging.error(f"Failed to store recording metadata: {e}")
            return False

    def update_metadata_completed(self, egress_id: str, filename: Optional[str] = None) -> bool:
        """Update metadata when recording completes"""
        try:
            metadata_file = self.recordings_dir / f"EG_{egress_id}.json"

            if not metadata_file.exists():
                logging.warning(f"Metadata file not found: {metadata_file}")
                return False

            with open(metadata_file, 'r') as f:
                metadata = json.load(f)

            metadata["status"] = "completed"
            metadata["completed_at"] = datetime.utcnow().isoformat()

            if filename:
                metadata["filename"] = filename

            # Update file size if file exists
            filepath = metadata.get("filepath")
            if filepath and os.path.exists(filepath):
                metadata["file_size"] = os.path.getsize(filepath)

            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)

            logging.info(f"Recording metadata updated: {egress_id}")
            return True

        except Exception as e:
            logging.error(f"Failed to update recording metadata: {e}")
            return False

    def find_recording_by_egress(self, egress_id: str) -> Optional[Dict[str, Any]]:
        """Find recording metadata by egress ID"""
        try:
            metadata_file = self.recordings_dir / f"EG_{egress_id}.json"

            if metadata_file.exists():
                with open(metadata_file, 'r') as f:
                    return json.load(f)

        except Exception as e:
            logging.error(f"Failed to find recording by egress {egress_id}: {e}")

        return None

    def find_recording_by_room(self, room_name: str) -> Optional[Dict[str, Any]]:
        """Find recording by room name"""
        try:
            for metadata_file in self.recordings_dir.glob("EG_*.json"):
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)

                if metadata.get("room_name") == room_name:
                    return metadata

        except Exception as e:
            logging.error(f"Failed to find recording by room {room_name}: {e}")

        return None

    def list_recordings(self, status: Optional[str] = None) -> list:
        """List all recordings"""
        recordings = []

        try:
            for metadata_file in self.recordings_dir.glob("EG_*.json"):
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)

                if status is None or metadata.get("status") == status:
                    recordings.append(metadata)

        except Exception as e:
            logging.error(f"Failed to list recordings: {e}")

        return recordings

    def cleanup_old_recordings(self, days_old: int = 7) -> int:
        """Clean up old recording files and metadata"""
        cleaned_count = 0

        try:
            cutoff_time = datetime.utcnow().timestamp() - (days_old * 24 * 60 * 60)

            for metadata_file in self.recordings_dir.glob("EG_*.json"):
                try:
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)

                    # Check if recording is old enough
                    started_at = metadata.get("started_at")
                    if started_at:
                        started_timestamp = datetime.fromisoformat(started_at.replace('Z', '+00:00')).timestamp()
                        if started_timestamp < cutoff_time:
                            # Remove metadata file
                            metadata_file.unlink()

                            # Remove recording file if it exists
                            filepath = metadata.get("filepath")
                            if filepath and os.path.exists(filepath):
                                os.remove(filepath)

                            cleaned_count += 1
                            logging.info(f"Cleaned up old recording: {metadata_file}")

                except Exception as e:
                    logging.warning(f"Failed to process metadata file {metadata_file}: {e}")

        except Exception as e:
            logging.error(f"Failed to cleanup old recordings: {e}")

        return cleaned_count

# Global instance
recording_manager = RecordingManager()
```

## **3. Integration in Main Agent (`cagent.py`)**

Add this to your main agent entrypoint:

```python
import os
from dotenv import load_dotenv
import logging
from egress_manager import egress_manager

from livekit.agents import AgentSession, Agent, JobContext
# ... other imports ...

async def entrypoint(ctx: JobContext):
    # Initialize egress manager
    await egress_manager.initialize()

    # Start recording for the room
    egress_id = await egress_manager.start_recording(ctx.room.name, audio_only=True)

    if egress_id:
        logging.info(f"Recording started with egress_id: {egress_id}")
        # Store egress_id for later use (e.g., in session_manager)
        campaign_metadata = {"egressId": egress_id}
    else:
        logging.warning("Failed to start recording")

    # ... rest of your agent logic ...

    # Recording will automatically stop when the session ends
    # (handled by LiveKit's egress completion webhook)
```

## **4. Docker Deployment Setup**

### **A. `docker-compose.egress.yml`**
```yaml
version: '3.8'

services:
  livekit-egress:
    image: livekit/egress:latest
    container_name: livekit-egress
    volumes:
      - ./recordings:/recordings
      - ./egress.yaml:/egress.yaml
    environment:
      - EGRESS_CONFIG_FILE=/egress.yaml
    networks:
      - livekit-network
    restart: unless-stopped

  egress-manager:
    build:
      context: .
      dockerfile: Dockerfile.egress
    container_name: egress-manager
    environment:
      - LIVEKIT_URL=${LIVEKIT_URL}
      - LIVEKIT_API_KEY=${LIVEKIT_API_KEY}
      - LIVEKIT_API_SECRET=${LIVEKIT_API_SECRET}
      - AZURE_STORAGE_CONNECTION_STRING=${AZURE_STORAGE_CONNECTION_STRING}
      - AZURE_CONTAINER_NAME=livekit-recordings
      - WEBHOOK_SECRET=${WEBHOOK_SECRET}
    volumes:
      - ./recordings:/app/recordings
    ports:
      - "8081:8081"
    depends_on:
      - livekit-egress
    networks:
      - livekit-network
    restart: unless-stopped

networks:
  livekit-network:
    external: true
```

### **B. `Dockerfile.egress`**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY egress_api.py .
COPY egress_manager.py .
COPY azure_storage.py .
COPY recording_manager.py .

# Create recordings directory
RUN mkdir -p recordings

EXPOSE 8081

CMD ["python", "egress_api.py"]
```

### **C. `egress.yaml`** - LiveKit Egress Configuration
```yaml
# LiveKit Egress Service Configuration
api_key: "your-api-key"
api_secret: "your-api-secret"
ws_url: "ws://livekit-server:7880"

# Redis configuration (must match LiveKit server)
redis:
  address: "redis:6379"

# Azure Storage configuration
azure:
  account_name: "your-storage-account"
  account_key: "your-account-key"
  container_name: "livekit-recordings"

# Recording settings
recording:
  # Temporary storage path
  path: "/recordings"
  # Maximum recording duration (seconds)
  max_duration: 3600
  # File format
  format: "mp4"
```

## **5. Environment Variables**

Add to your `.env` file:

```env
# LiveKit Configuration
LIVEKIT_URL=ws://localhost:7880
LIVEKIT_API_KEY=your-api-key
LIVEKIT_API_SECRET=your-api-secret

# Azure Storage (optional)
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...;EndpointSuffix=core.windows.net
AZURE_CONTAINER_NAME=livekit-recordings

# Egress Manager
WEBHOOK_SECRET=your-webhook-secret
AUTO_UPLOAD_TO_CLOUD=false

# Recording Settings
RECORDINGS_DIR=./recordings
```

## **6. Directory Structure**

Create these directories:
```
your-project/
├── recordings/              # Local recording storage
├── egress_manager.py        # Main egress management
├── egress_api.py           # REST API for egress control
├── azure_storage.py        # Cloud storage utilities
├── recording_manager.py    # Recording metadata management
├── docker-compose.egress.yml # Egress deployment
├── Dockerfile.egress       # Egress container
├── egress.yaml            # LiveKit egress config
└── cagent.py              # Main agent (modified)
```

## **7. Key Features Implemented**

1. **Automatic Recording**: Starts recording when agent session begins
2. **Cloud Storage**: Optional Azure Blob Storage integration
3. **Metadata Management**: Tracks recording lifecycle and metadata
4. **REST API**: HTTP endpoints for recording control
5. **Webhook Integration**: Handles LiveKit egress completion events
6. **Cleanup Utilities**: Automatic cleanup of old recordings
7. **Docker Deployment**: Complete containerized setup

## **8. Usage Examples**

### **Start Recording Programmatically**
```python
from egress_manager import egress_manager

# Initialize
await egress_manager.initialize()

# Start recording
egress_id = await egress_manager.start_recording("room-name", audio_only=True)

# Stop recording
await egress_manager.stop_recording(egress_id)
```

### **Upload to Cloud**
```python
from azure_storage import azure_manager

# Upload recording
cloud_url = await azure_manager.upload_file("/path/to/recording.mp4")
```

### **REST API Endpoints**
```bash
# Start recording
curl -X POST http://localhost:8081/recording/start \
  -H "Content-Type: application/json" \
  -d '{"room_name": "room-123", "audio_only": true}'

# Stop recording
curl -X POST http://localhost:8081/recording/stop \
  -H "Content-Type: application/json" \
  -d '{"egress_id": "EG_abc123"}'

# List recordings
curl http://localhost:8081/recordings
```

## **9. Deployment Commands**

### **Start Egress Services**
```bash
# Start LiveKit egress service
docker run -d --name livekit-egress \
  --network livekit-network \
  -v $(pwd)/recordings:/recordings \
  -v $(pwd)/egress.yaml:/egress.yaml \
  livekit/egress:latest

# Start egress manager API
docker-compose -f docker-compose.egress.yml up -d egress-manager
```

### **Setup Azure Storage**
```bash
# Create storage container
python -c "
from azure_storage import azure_manager
import asyncio
asyncio.run(azure_manager.ensure_container_exists())
"
```

This setup provides a complete, production-ready egress recording system that captures all voice conversations, supports cloud storage, and includes comprehensive management and cleanup utilities.</content>
<parameter name="filePath">c:\Users\int10281\Desktop\Github\xeny-livekit-voicebot\docs\egress_setup_guide.md