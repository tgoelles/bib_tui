import click

from bib_tui import __version__


@click.command()
@click.version_option(__version__, prog_name="bib-tui")
@click.argument("bib_file", type=click.Path(exists=True, readable=True, dir_okay=False))
def main(bib_file: str) -> None:
    """Browse and manage BibTeX bibliography files.

    BIB_FILE is the path to the .bib file to open.

    \b
    Examples:
      bib-tui references.bib
      bib-tui ~/papers/MyCollection.bib

    \b
    Docs & source: https://github.com/tgoelles/bib_tui
    """
    from bib_tui.app import BibTuiApp

    BibTuiApp(bib_file).run()


if __name__ == "__main__":
    main()
