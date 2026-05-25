# Syphon
Syphon is a utility designed to asynchronously download and archive video streams. It focuses on reliability and data health by automating the entire lifecycle—from the initial fetch to final export—ensuring every file is verified for integrity before it hits your storage.

Key features:

Asynchronous Processing: Efficiently handles multiple download tasks in the background without blocking the system.

Integrity Verification: Uses FFmpeg to test every file, automatically discarding corrupted downloads to ensure your collection stays clean.

Secure Isolation: Built to run in containers, keeping your host system isolated and clean.

Persistent State: Built-in telemetry tracks progress, speed, and ETA, allowing you to resume or cancel tasks at any time.

## How to use:
go into the main Syphon/ directory and run:
```docker compose up --build``` This should build and run the container, after that you can paste your links into the dashboard at localhost:8000
and it should look something like this:
<img width="2400" height="1075" alt="image" src="https://github.com/user-attachments/assets/3b6aea01-c20e-4fc0-a6c7-4f2dba600218" />

after your files are verified, you can find them under media/exports

