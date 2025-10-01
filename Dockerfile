# Use official Python 3.13 pre-release
FROM python:3.13

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# No need to COPY code if you mount volume at runtime
# But keep this for clarity
COPY . .

CMD ["python", "trading_script.py"]