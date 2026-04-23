FROM python:3.11-slim
WORKDIR /app

COPY reference/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY proto/ /app/proto/
COPY reference/ /app/reference/

WORKDIR /app/reference
RUN python -m grpc_tools.protoc -I../proto --python_out=. ../proto/message.proto

CMD ["python", "-u", "reference.py"]
