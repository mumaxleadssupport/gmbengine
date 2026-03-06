from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import subprocess
import os
import json
import sys
import threading

app = FastAPI(title="MuMax Leads Engine")

# Resolve absolute paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TMP_DIR = os.path.join(BASE_DIR, ".tmp")
HISTORY_DIR = os.path.join(TMP_DIR, "history")

print(f"--- SERVER STARTING ---")
print(f"BASE_DIR: {BASE_DIR}")
print(f"Checking for static/index.html at: {os.path.join(STATIC_DIR, 'index.html')}")
if os.path.exists(os.path.join(STATIC_DIR, "index.html")):
    print("✅ Found index.html")
else:
    print("❌ ERROR: index.html NOT FOUND at that path.")
    # List files to debug
    print(f"Files in BASE_DIR ({BASE_DIR}): {os.listdir(BASE_DIR)}")
    if os.path.exists(os.path.join(BASE_DIR, "static")):
        print(f"Files in static folder: {os.listdir(os.path.join(BASE_DIR, 'static'))}")

# Create directories if they don't exist
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(TMP_DIR, exist_ok=True)
os.makedirs(HISTORY_DIR, exist_ok=True)

# Global status tracking
task_status = {
    "running": False,
    "current_step": "idle",
    "error": None,
    "last_file": None
}

# Mount static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/debug")
def list_files():
    """Helpful for debugging Render file structure"""
    files_tree = {}
    for root, dirs, files in os.walk(BASE_DIR):
        # Skip .venv and __pycache__
        if ".venv" in dirs: dirs.remove(".venv")
        if "__pycache__" in dirs: dirs.remove("__pycache__")
        
        rel_path = os.path.relpath(root, BASE_DIR)
        files_tree[rel_path] = {
            "dirs": dirs,
            "files": files
        }
    return {
        "cwd": os.getcwd(),
        "base_dir": BASE_DIR,
        "tree": files_tree
    }

class ScrapeRequest(BaseModel):
    query: str
    limit: int = 10

def run_pipeline_task(query: str, limit: int):
    global task_status
    # On Render, it's safer to use python -m ... or just python
    python_exe = "python"
    task_status["running"] = True
    task_status["error"] = None
    
    try:
        # 1. Scrape
        task_status["current_step"] = f"Scraping GMB Listings (Query: '{query}')..."
        scrape_script = os.path.join(BASE_DIR, "execution", "scrape_gmb.py")
        gmb_leads_file = os.path.join(TMP_DIR, "gmb_leads.txt")
        subprocess.run(
            [python_exe, scrape_script, "--query", query, "--limit", str(limit), "--output", gmb_leads_file],
            check=True
        )
        
        # 2. Enrich
        task_status["current_step"] = "Visiting websites and scouring emails..."
        enrich_script = os.path.join(BASE_DIR, "execution", "enrich_leads.py")
        enriched_leads_file = os.path.join(TMP_DIR, "enriched_leads.txt")
        subprocess.run(
            [python_exe, enrich_script, "--input", gmb_leads_file, "--output", enriched_leads_file],
            check=True
        )
        
        # 3. Export to CSV
        task_status["current_step"] = "Polishing and finalizing CSV export..."
        export_script = os.path.join(BASE_DIR, "execution", "export_csv.py")
        export_csv_file = os.path.join(TMP_DIR, "leads_export.csv")
        subprocess.run(
            [python_exe, export_script, "--input", enriched_leads_file, "--output", export_csv_file],
            check=True
        )
        
        # 4. Save to history
        import shutil
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_query = "".join([c if c.isalnum() else "_" for c in query])
        history_filename = f"history_{timestamp}_{safe_query}.csv"
        history_file_path = os.path.join(HISTORY_DIR, history_filename)
        shutil.copy(export_csv_file, history_file_path)
        
        task_status["last_file"] = history_filename
        task_status["current_step"] = "completed"
    except Exception as e:
        task_status["error"] = str(e)
        task_status["current_step"] = "failed"
    finally:
        task_status["running"] = False

@app.get("/")
def read_root():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"error": "index.html not found", "path_searched": index_path, "current_dir": os.getcwd()}

@app.post("/api/scrape")
def scrape_and_enrich(req: ScrapeRequest, background_tasks: BackgroundTasks):
    global task_status
    if task_status["running"]:
        return {"status": "error", "message": "A scrape is already in progress"}
    
    # Reset status
    task_status["running"] = True
    task_status["current_step"] = "Starting engine..."
    task_status["error"] = None
    
    background_tasks.add_task(run_pipeline_task, req.query, req.limit)
    return {"status": "accepted", "message": "Scrape started in background"}

@app.get("/api/status")
def get_status():
    return task_status

@app.get("/api/results")
def get_results(file: str = None):
    file_path = os.path.join(HISTORY_DIR, file) if file else os.path.join(TMP_DIR, "leads_export.csv")
    if not os.path.exists(file_path):
        return {"data": []}
    
    # Simple CSV parser to return JSON data back to the frontend table
    import csv
    results = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                results.append(row)
        return {"data": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to read results")

@app.get("/api/history")
def get_history():
    history_files = []
    try:
        if not os.path.exists(HISTORY_DIR): return {"history": []}
        for f in os.listdir(HISTORY_DIR):
            if f.endswith(".csv"):
                # Extract date and query
                parts = f.replace(".csv", "").split("_")
                if len(parts) >= 4:
                    date_str = f"{parts[1][:4]}-{parts[1][4:6]}-{parts[1][6:]}"
                    time_str = f"{parts[2][:2]}:{parts[2][2:4]}:{parts[2][4:]}"
                    query = "_".join(parts[3:])
                    history_files.append({
                        "filename": f,
                        "date": f"{date_str} {time_str}",
                        "query": query.replace("_", " ")
                    })
        # Sort by most recent first
        history_files.sort(key=lambda x: x["filename"], reverse=True)
        return {"history": history_files}
    except Exception as e:
        return {"history": [], "error": str(e)}

@app.get("/api/download")
def download_csv(file: str = None):
    file_path = os.path.join(HISTORY_DIR, file) if file else os.path.join(TMP_DIR, "leads_export.csv")
    if os.path.exists(file_path):
        return FileResponse(path=file_path, filename="mumax_leads_export.csv", media_type="text/csv")
    raise HTTPException(status_code=404, detail="Export file not found")

if __name__ == "__main__":
    import uvicorn
    # Use PORT environment variable if it exists (for cloud deployments like Render/Heroku)
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
