FROM python:3.11-alpine

WORKDIR /app

# Create a non-privileged user to run the container
RUN addgroup -S appgroup && adduser -S appuser -G appgroup

# Copy requirements and install optional dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy sync script
COPY sync.py .
COPY checkwarranty_snipeit_sync ./checkwarranty_snipeit_sync

USER appuser

ENTRYPOINT ["python", "sync.py"]
CMD ["--limit", "100"]
