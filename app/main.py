from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import asyncio
import database
import downloader

MAX_CONCURRENT_TASKS = 12
semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)

app = FastAPI(title="Portable Media Downloader")
templates = Jinja2Templates(directory="templates")

class DownloadRequest(BaseModel):
    url: str
    referer: str = None
    origin: str = None
    title: str = None

async def worker(task_id: int, url: str, referer: str, origin: str, title: str):
    async with semaphore:
        await downloader.process_download(task_id, url, referer, origin, title)

@app.on_event("startup")
async def startup_event():
    database.init_db()
    pending_tasks = database.get_queued_tasks()
    for task in pending_tasks:
        asyncio.create_task(worker(task['id'], task['url'], task['referer'], task['origin'], task['title']))

@app.get("/")
async def serve_dashboard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/add")
async def add_link(req: DownloadRequest):
    task_id = database.add_task(req.url, req.referer, req.origin, req.title)
    asyncio.create_task(worker(task_id, req.url, req.referer, req.origin, req.title))
    return {"status": "success", "task_id": task_id}

@app.post("/api/cancel/{task_id}")
async def cancel_link(task_id: int):
    success = await downloader.cancel_task(task_id)
    if not success:
        database.update_status(task_id, "CANCELED")
    return {"status": "canceled"}

class RefreshRequest(BaseModel):
    url: str

@app.post("/api/refresh/{task_id}")
async def refresh_link(task_id: int, req: RefreshRequest):
    # 1. Fetch the old task data (we need the original title, referer, etc.)
    task = database.get_task(task_id)
    if not task:
        return {"status": "error", "msg": "Task not found"}
        
    # 2. Update the database with the fresh URL
    database.update_task_source(task_id, req.url)
    
    # 3. Reset the status so the UI knows it's active again
    database.update_status(task_id, "QUEUED", progress="0", speed="", size="", eta="")
    
    # 4. Restart the worker. yt-dlp's --continue flag will handle the rest!
    asyncio.create_task(worker(task_id, req.url, task['referer'], task['origin'], task['title']))
    
    return {"status": "success"}

@app.delete("/api/clear")
async def clear_history():
    database.clear_history()
    return {"status": "cleared"}

@app.get("/api/tasks")
async def get_tasks():
    with database.get_db() as conn:
        tasks = conn.execute("SELECT * FROM queue ORDER BY created_at DESC").fetchall()
        return [dict(task) for task in tasks]