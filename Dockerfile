FROM python:3.11-slim

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir .

ENV MCP_HTTP_HOST=0.0.0.0
ENV MCP_HTTP_PORT=8080

EXPOSE 8080

CMD ["telugu-mcp-http"]
