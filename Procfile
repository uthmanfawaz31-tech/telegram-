web: sh -c "if [ -d 'backend' ]; then cd backend && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}; else uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}; fi"
