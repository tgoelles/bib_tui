default:
    @just --list

# Bump patch version, tag, and push
patch:
    uv version --bump patch
    git add pyproject.toml uv.lock CHANGELOG.md
    git commit -m "bump version to $(uv version --short)"
    git tag "v$(uv version --short)"
    git push
    git push --tags

minor:
    uv version --bump minor
    git add pyproject.toml uv.lock CHANGELOG.md
    git commit -m "bump version to $(uv version --short)"
    git tag "v$(uv version --short)"
    git push
    git push --tags

# run with MyCollection.bib example
run:
  uv run bibtui tests/bib_examples/MyCollection.bib

# run without a file
run_nofile:
  uv run bibtui

# run with live reload during development (Textual dev mode)
dev:
  uv run textual run --dev src/bibtui/main.py -- tests/bib_examples/MyCollection.bib

# delete config files to test first run experience
fresh:
  rm -r $HOME/.config/bibtui

test:
  uv run pytest -v tests

# lint the source with ruff
lint:
  uv run ruff check src/

# serve the docs locally with live reload at http://127.0.0.1:8000
docs:
  uv run --group docs mkdocs serve

# build the docs site into ./site
docs-build:
  uv run --group docs mkdocs build --strict

# regenerate the documentation screenshots from the live app
screenshots:
  uv run python scripts/generate_screenshots.py