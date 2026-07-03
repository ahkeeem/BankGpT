#!/usr/bin/env python3
"""
Real-world Data Sourcing Pipeline for Nigerian Financial/Regulatory Knowledge Base.
Downloads official regulatory PDFs and scrapes bank FAQs, then indexes them via the running API.
"""

import os
import sys
import time
import httpx

API_BASE_URL = "http://localhost:8000"
ORG_ID = "demo_org"

# Real-world high-value Wikipedia resources covering Nigerian banking & economy
URL_SOURCES = [
    {
        "name": "Central Bank of Nigeria",
        "url": "https://en.wikipedia.org/wiki/Central_Bank_of_Nigeria"
    },
    {
        "name": "Economy of Nigeria",
        "url": "https://en.wikipedia.org/wiki/Economy_of_Nigeria"
    },
    {
        "name": "United Bank for Africa",
        "url": "https://en.wikipedia.org/wiki/United_Bank_for_Africa"
    },
    {
        "name": "Guaranty Trust Holding Company",
        "url": "https://en.wikipedia.org/wiki/Guaranty_Trust_Holding_Company_PLC"
    }
]

# Real-world digitally-born, text-searchable regulatory PDFs (FIRS & CBN)
PDF_SOURCES = [
    {
        "name": "CBN_FX_Spread_Circular_2024.pdf",
        "url": "https://www.cbn.gov.ng/out/2024/fmd/fmd_dir_pub_cir_001_012.pdf"
    },
    {
        "name": "FIRS_Nigeria_Finance_Act_2020.pdf",
        "url": "https://www.firs.gov.ng/wp-content/uploads/2021/02/Finance-Act-2020.pdf"
    }
]


def check_backend_running():
    """Verify backend is healthy and responding."""
    try:
        response = httpx.get(f"{API_BASE_URL}/health", timeout=5.0)
        return response.status_code == 200
    except Exception:
        return False


def get_auth_token():
    """Authenticate and get a bearer token."""
    url = f"{API_BASE_URL}/api/v1/auth/token"
    payload = {"username": "admin", "password": "admin123"}
    try:
        response = httpx.post(url, json=payload, timeout=10.0)
        response.raise_for_status()
        token = response.json().get("access_token")
        print("🔐 Authenticated successfully.")
        return token
    except Exception as e:
        print(f"❌ Auth failed: {e}")
        return None


def ingest_url(token, name, url):
    """Post a URL to the ingestion pipeline."""
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"url": url, "org_id": ORG_ID}
    api_url = f"{API_BASE_URL}/api/v1/ingestion/url"
    
    print(f"🌐 Ingesting URL: {name} ({url})...")
    try:
        response = httpx.post(api_url, json=payload, headers=headers, timeout=120.0)
        if response.status_code == 200:
            res_data = response.json()
            print(f"✅ Indexed: {res_data.get('name')} ({res_data.get('chunk_count')} chunks)")
        else:
            print(f"❌ Failed to ingest {name}: {response.text}")
    except Exception as e:
        print(f"❌ Error ingesting {name}: {e}")


def download_and_ingest_pdf(token, name, url):
    """Download a PDF locally and upload to the ingestion endpoint."""
    headers = {"Authorization": f"Bearer {token}"}
    
    # We will write the file in a temp path inside the user's workspace
    temp_dir = "/Users/hakeem/Documents/MyProject/BankGPT/knowledge-base-mvp/backend/data/temp"
    os.makedirs(temp_dir, exist_ok=True)
    temp_path = os.path.join(temp_dir, name)
    
    print(f"📥 Downloading PDF: {name} from {url}...")
    try:
        # Download file with custom headers to prevent bot-blocking
        client = httpx.Client(follow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
        response = client.get(url, timeout=60.0)
        response.raise_for_status()
        
        with open(temp_path, "wb") as f:
            f.write(response.content)
        print(f"💾 Downloaded to {temp_path} ({len(response.content)} bytes)")
        
        # Upload
        print(f"⬆️ Uploading and indexing {name}...")
        api_url = f"{API_BASE_URL}/api/v1/ingestion/upload"
        with open(temp_path, "rb") as f:
            files = {"file": (name, f, "application/pdf")}
            data = {"org_id": ORG_ID}
            upload_response = httpx.post(api_url, data=data, files=files, headers=headers, timeout=300.0)
            
        if upload_response.status_code == 200:
            res_data = upload_response.json()
            print(f"✅ Indexed: {res_data.get('name')} ({res_data.get('chunk_count')} chunks)")
        else:
            print(f"❌ Ingestion failed: {upload_response.text}")
            
    except Exception as e:
        print(f"❌ Error processing PDF {name}: {e}")
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


def main():
    print("🚀 Starting real-world data sourcing pipeline for Nigeria ecosystem...")
    
    if not check_backend_running():
        print(f"❌ Error: Backend is not running at {API_BASE_URL}. Start it first with: uvicorn app.main:app")
        sys.exit(1)
        
    token = get_auth_token()
    if not token:
        print("❌ Error: Could not get authentication token.")
        sys.exit(1)

    print("\n--- Phase 1: Ingesting Web Page Sources ---")
    for source in URL_SOURCES:
        ingest_url(token, source["name"], source["url"])
        time.sleep(2)  # Avoid hammering servers

    print("\n--- Phase 2: Downloading & Ingesting Regulatory PDFs ---")
    for source in PDF_SOURCES:
        download_and_ingest_pdf(token, source["name"], source["url"])
        time.sleep(2)
        
    print("\n🎉 Pipeline completed.")


if __name__ == "__main__":
    main()
