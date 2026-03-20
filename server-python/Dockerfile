FROM python:3.11-slim
WORKDIR /app

COPY server-python/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY proto/ /app/proto/
COPY server-python/ /app/server-python/

WORKDIR /app/server-python
RUN python -m grpc_tools.protoc -I../proto --python_out=. ../proto/message.proto

CMD ["python", "-u", "server.py"]
