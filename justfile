default:
    @just --list

# Bump patch version, tag, and push
release-patch:
    uv version --bump patch
    git add pyproject.toml uv.lock
    git commit -m "bump version to $(uv version --short)"
    git tag "v$(uv version --short)"
    git push
    git push --tags

# run with MyCollection.bib example
run:
  uv run bibtui tests/bib_examples/MyCollection.bib

# delete config files to test first run experience
fresh:
  rm -r $HOME/.config/bibtui