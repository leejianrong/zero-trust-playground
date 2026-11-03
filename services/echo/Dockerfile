FROM python:3.12-slim
RUN pip install --no-cache-dir spiffe==0.4.0
COPY app.py /app/app.py
ENTRYPOINT ["python", "/app/app.py"]
