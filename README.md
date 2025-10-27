# Telugu-Subramanyam MCP Server

This repository hosts the **Telugu-Subramanyam MCP** runtime – a Telugu purohita agent that delivers fully localized ritual guidance for Andhra and Telangana traditions.

## Prerequisites

* Python 3.11+
* [pipx](https://pypa.github.io/pipx/) or `pip`
* Git (to clone and push changes to GitHub)

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install .[dev]
```

## Running the MCP server

The project exposes a console script once installed:

```bash
# ensure the virtual environment is active
pip install .
telugu-mcp-server
```

The server speaks the Model Context Protocol over stdio. Integrate it with your MCP-compatible client (for example, Claude Desktop) by pointing the client to the generated executable.

### HTTP + SSE transport

An HTTPS-friendly transport is also available via the `telugu-mcp-http` entry point. The server accepts optional `MCP_HTTP_HOST` and `MCP_HTTP_PORT` environment variables (defaults: `0.0.0.0:8000`).

```bash
pip install .
export MCP_HTTP_PORT=8080
telugu-mcp-http
```

With the server running, the manifest and tools can be queried via HTTP:

```bash
curl http://localhost:8080/manifest.json
curl http://localhost:8080/ceremonies
curl http://localhost:8080/ceremonies/upanayanam
curl -X POST http://localhost:8080/tools/varalakshmi_vratam
```

Server-sent events are streamed from `/ceremonies/<tool>/stream` for clients that prefer SSE.

## Automated tests

```bash
pytest
```

## Downloading ritual source archives

The repository includes a manifest describing authoritative Telugu ritual sources. To copy the referenced documents locally and
bundle them as a zip archive, run:

```bash
python -m corpus.download --manifest data/source_manifest.json --dest downloads --zip-output downloads/sources.zip
```

The command respects existing files; pass `--overwrite` to refresh previously downloaded content.

## Building distributable artifacts

The repository is configured for `setuptools`. Generate a source distribution and wheel with:

```bash
python -m build
```

Artifacts will be written to the `dist/` directory.

## Container image & GitHub deployment

This repository includes a `Dockerfile` that serves the HTTP transport on port `8080`.

```bash
docker build -t telugu-subramanyam-mcp .
docker run -p 8080:8080 telugu-subramanyam-mcp
```

The [`deploy.yml`](.github/workflows/deploy.yml) workflow publishes the container to GitHub Container Registry (`ghcr.io/<owner>/telugu-subramanyam-mcp:latest`) on every push to `main` or manual dispatch. Authenticate with `docker login ghcr.io` and run the image directly or promote it to your hosting provider of choice (Fly.io, Railway, Render, etc.).

## Agent Builder integration

1. Deploy the container image (or run `telugu-mcp-http`) on a public host that serves HTTPS, e.g. Fly.io or a Kubernetes ingress.
2. Ensure the manifest is reachable at `https://<your-domain>/manifest.json`. The Agent Builder expects this HTTPS endpoint alongside `/ceremonies` and `/tools/<id>` routes.
3. Provide the HTTPS base URL plus credentials (if any) to the OpenAI Agent Builder configuration.

Example target URL (replace with your deployment):

```
https://telugu-subramanyam.example.com/manifest.json
```

Once deployed, OpenAI Agent Builder can call `https://telugu-subramanyam.example.com/tools/upanayanam` to retrieve the structured Telugu guidance.

## Publishing to GitHub

1. Create a new GitHub repository and copy its clone URL.
2. Set the remote for this project:
   ```bash
   git remote add origin <YOUR-REMOTE-URL>
   ```
3. Push the current branch:
   ```bash
   git push -u origin work
   ```
4. Subsequent updates can be pushed with `git push`.

## Continuous Integration

GitHub Actions automatically runs the test suite and builds the distributables on every push and pull request via [`.github/workflows/ci.yml`](.github/workflows/ci.yml).
