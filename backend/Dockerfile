FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN CHROMIUM_PATH=$(find /ms-playwright -name "chrome" -type f | head -1) && \
    echo "CHROMIUM_PATH=$CHROMIUM_PATH" >> /etc/environment

COPY . .

RUN chown -R 1000:1000 /app
USER 1000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
