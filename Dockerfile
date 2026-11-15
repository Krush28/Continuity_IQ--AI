# Works on Hugging Face Spaces (Docker), Railway, Fly.io or any Docker host.
FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend backend
COPY frontend/dist frontend/dist
COPY sample_docs sample_docs
ENV SEED_DEMO=true DEMO_MODE=true PORT=7860
EXPOSE 7860
CMD ["sh", "-c", "cd backend && uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
