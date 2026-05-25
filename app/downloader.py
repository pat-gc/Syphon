import asyncio
import os
import re
import shutil
import time
from database import update_status, get_task

YT_DLP_PATH = "/usr/local/bin/yt-dlp"
ACTIVE_PROCESSES = {}

async def verify_file(file_path: str) -> bool:
    cmd = ["ffmpeg", "-v", "error", "-xerror", "-i", file_path, "-f", "null", "-"]
    process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    await process.communicate()
    
    if process.returncode == 0:
        return True
    if os.path.exists(file_path):
        os.remove(file_path)
    return False

def sanitize_filename(name: str, task_id: int) -> str:
    if not name:
        return f"movie_{task_id}"
    clean_name = re.sub(r'[^\w\-_\. ]', '_', name)
    return clean_name.strip() or f"movie_{task_id}"

async def cancel_task(task_id: int):
    if task_id in ACTIVE_PROCESSES:
        ACTIVE_PROCESSES[task_id].terminate()
        update_status(task_id, "CANCELED")
        return True
    return False

async def process_download(task_id: int, url: str, referer: str, origin: str, title: str, auto_verify: bool = True):
    update_status(task_id, "DOWNLOADING", progress="0", speed="", size="", eta="")
    
    safe_title = sanitize_filename(title, task_id)
    work_dir = "/media"
    export_dir = "/media/exports"
    os.makedirs(export_dir, exist_ok=True)
    
    output_template = f"{work_dir}/{safe_title}.%(ext)s"
    
    cmd = [
        YT_DLP_PATH, 
        "--newline", 
        "--no-check-certificate", 
        "--impersonate", "chrome", 
        "--continue",
        "--no-overwrites",
        "-o", output_template
    ]
    if referer: cmd.extend(["--referer", referer])
    if origin: cmd.extend(["--add-header", f"Origin: {origin}"])
    cmd.append(url)

    process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    ACTIVE_PROCESSES[task_id] = process

    last_update_time = 0.0

    while True:
        line = await process.stdout.readline()
        if not line: break
        line_str = line.decode('utf-8', errors='ignore')
        
        if "[download]" in line_str and "%" in line_str:
            perc_match = re.search(r'(\d+(?:\.\d+)?)%', line_str)
            if perc_match:
                current_time = time.time()
                if current_time - last_update_time > 1.0:
                    percentage = perc_match.group(1)
                    speed_match = re.search(r'at\s+([0-9\.\w]+/s)', line_str)
                    speed = speed_match.group(1) if speed_match else None
                    size_match = re.search(r'of\s+(.*?)(?:\s+at|\s+\()', line_str)
                    size = size_match.group(1).strip() if size_match else None
                    eta_match = re.search(r'ETA\s+([a-zA-Z0-9:]+)', line_str)
                    eta = eta_match.group(1) if eta_match else None
                    
                    update_status(task_id, "DOWNLOADING", progress=percentage, speed=speed, size=size, eta=eta)
                    last_update_time = current_time

    if task_id in ACTIVE_PROCESSES:
        del ACTIVE_PROCESSES[task_id]

    if get_status(task_id) == "CANCELED":
        return

    # NEW: Check if we should skip verification and leave it parked
    if not auto_verify:
        update_status(task_id, "AWAITING_VERIFICATION")
        return

    # Otherwise, proceed to automatic verification
    await verify_task(task_id)


async def verify_task(task_id: int):
    """Standalone function to verify a downloaded file and export it."""
    task = get_task(task_id)
    if not task:
        return
        
    update_status(task_id, "VERIFYING")
    
    safe_title = sanitize_filename(task['title'], task_id)
    work_dir = "/media"
    export_dir = "/media/exports"
    os.makedirs(export_dir, exist_ok=True)
    
    # Find the downloaded file
    downloaded_file = None
    for f in os.listdir(work_dir):
        if f.startswith(safe_title + ".") and not f.endswith(".part") and not f.endswith(".ytdl"):
            full_path = os.path.join(work_dir, f)
            if os.path.isfile(full_path):
                downloaded_file = full_path
                break
            
    if not downloaded_file:
        update_status(task_id, "FAILED")
        return

    # Run FFmpeg check
    is_valid = await verify_file(downloaded_file)
    if is_valid:
        final_export_path = os.path.join(export_dir, os.path.basename(downloaded_file))
        shutil.move(downloaded_file, final_export_path)
        update_status(task_id, "COMPLETED", file_path=final_export_path)
    else:
        update_status(task_id, "FAILED")

def get_status(task_id):
    import database
    with database.get_db() as conn:
        row = conn.execute("SELECT status FROM queue WHERE id = ?", (task_id,)).fetchone()
        return row['status'] if row else None