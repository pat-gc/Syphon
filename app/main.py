from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import asyncio
import database
import downloader

MAX_CONCURRENT_TASKS = 8
semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)

app = FastAPI(title="Syphon Media Downloader")
templates = Jinja2Templates(directory="templates")

class DownloadRequest(BaseModel):
    url: str
    referer: str = None
    origin: str = None
    title: str = None
    auto_verify: bool = True  

class RefreshRequest(BaseModel):
    url: str

class ToggleVerifyRequest(BaseModel):
    auto_verify: bool  

async def worker(task_id: int, url: str, referer: str, origin: str, title: str, auto_verify: bool):
    async with semaphore:
        await downloader.process_download(task_id, url, referer, origin, title, auto_verify)

@app.on_event("startup")
async def startup_event():
    database.init_db()
    pending_tasks = database.get_queued_tasks()
    for task in pending_tasks:
        # Explicitly cast to boolean: SQLite stores 1/0
        auto_verify = bool(task['auto_verify']) if 'auto_verify' in task.keys() else True
        asyncio.create_task(worker(task['id'], task['url'], task['referer'], task['origin'], task['title'], auto_verify))

@app.get("/")
async def serve_dashboard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/add")
async def add_link(req: DownloadRequest):
    task_id = database.add_task(req.url, req.referer, req.origin, req.title, req.auto_verify)
    asyncio.create_task(worker(task_id, req.url, req.referer, req.origin, req.title, req.auto_verify))
    return {"status": "success", "task_id": task_id}

@app.post("/api/cancel/{task_id}")
async def cancel_link(task_id: int):
    success = await downloader.cancel_task(task_id)
    if not success:
        database.update_status(task_id, "CANCELED")
    return {"status": "canceled"}

@app.post("/api/refresh/{task_id}")
async def refresh_link(task_id: int, req: RefreshRequest):
    task = database.get_task(task_id)
    if not task:
        return {"status": "error", "msg": "Task not found"}
        
    database.update_task_source(task_id, req.url)
    database.update_status(task_id, "QUEUED", progress="0", speed="", size="", eta="")
    
    auto_verify = bool(task['auto_verify']) if 'auto_verify' in task.keys() else True
    asyncio.create_task(worker(task_id, req.url, task['referer'], task['origin'], task['title'], auto_verify))
    
    return {"status": "success"}

@app.post("/api/verify/{task_id}")
async def verify_link(task_id: int):
    asyncio.create_task(downloader.verify_task(task_id))
    return {"status": "verifying"}

@app.post("/api/toggle_verify/{task_id}")
async def toggle_verify(task_id: int, req: ToggleVerifyRequest):
    with database.get_db() as conn:
        # SQLite uses 1 for True, 0 for False
        conn.execute("UPDATE queue SET auto_verify = ? WHERE id = ?", (int(req.auto_verify), task_id))
        conn.commit()
    return {"status": "success", "auto_verify": req.auto_verify}

@app.delete("/api/clear")
async def clear_history():
    database.clear_history()
    return {"status": "cleared"}

@app.get("/api/tasks")
async def get_tasks():
    with database.get_db() as conn:
        tasks = conn.execute("SELECT * FROM queue ORDER BY created_at DESC").fetchall()
        return [dict(task) for task in tasks]