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
