FROM python:3.12-slim

# Security: Non-root user setup
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# Create persistent data directory and set permissions
RUN mkdir -p /data && chown -R appuser:appuser /data

# Set Python path so pytest and application import 'app' correctly
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source, static assets, diagrams, documentation, and test suite
COPY app/ ./app/
COPY tests/ ./tests/
COPY static/ ./static/
COPY diagrams/ ./diagrams/
COPY README.md .
COPY AI_PROMPTS.md .
COPY pytest.ini .

# Run security checks and unit tests during image build
RUN bandit -r app/ -q || true
RUN python -m pytest --cov=app --cov-report=term-missing

# Set ownership to non-root user
RUN chown -R appuser:appuser /app /data
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
