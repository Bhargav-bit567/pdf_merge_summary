FROM python:3.12-slim

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

# Point at an Ollama server reachable from the container, e.g.
#   docker run -p 8000:8000 -e OLLAMA_URL=http://host.docker.internal:11434 pdf-summarizer
ENV OLLAMA_URL=http://host.docker.internal:11434 \
    OLLAMA_MODEL=llama3.2

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
