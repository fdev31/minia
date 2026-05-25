install:
    uv sync --editable --extra tts,stt,mcp,dev

unidic:
    uv run python -m unidic download

upgrade:
    uv sync --editable --extra tts,stt,mcp,dev --upgrade

clean:
    find . -name __pycache__ -type d -exec rm -rf {} +
    find . -name '*.egg-info' -type d -exec rm -rf {} +
    find . -name .mypy_cache -type d -exec rm -fr {} +

test:
    uv run pytest tests/

mypy:
    uv run mypy --check-untyped-defs src

lint:
    uv run ruff format src
    uv run ruff check --fix src

mother:
    uv run minia

tts:
    uv run minia-tts

speak text:
    uv run minia-tts-client {{ text }}

stop-speak:
    uv run minia-tts-client --stop

serve:
    uv run minia-server

audio:
    uv run minia-chatloop

cli:
    uv run minia-client

web:
    uv run minia-web
