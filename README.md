# PDF Merge & Summary

Free, local PDF summarizer and merger. Files stay on your PC; summaries use Ollama running locally.

## Run on Windows

1. Install Python 3.10+ and [Ollama](https://ollama.com/download).
2. Pull the model once:
   ```powershell
   ollama pull llama3.2:3b
   ```
3. Run `run.bat`.
4. Open http://localhost:8000.

`run.bat` creates `.venv` and installs dependencies on first run. Keep Ollama running.

## Phone on same Wi-Fi

Run `ipconfig` on the PC, then open `http://<PC-IPv4-address>:8000` on your phone. Allow Python through Windows Firewall on private networks if prompted. This is local-network access, not public hosting.

## Features

- Summarize PDFs up to 100 MB, including large documents using chunked summaries.
- Merge multiple PDFs in the selected order and download one PDF.
- Quick, key-point, and detailed summary modes.

## Deployment note

Public hosting needs a reachable inference service. Local Ollama on your PC is not available to Render or Vercel automatically. Do not expose this unauthenticated app to the public internet; add authentication and choose a hosted inference provider or secured private server first.
