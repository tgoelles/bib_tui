# Working as a team

Most reference managers lock your library inside an account or a proprietary
database, then bolt "sharing" on top. bibtui takes the opposite approach: your
library is a **plain `.bib` text file**, so you can collaborate with the tools
your research group already trusts — Git and GitHub (or GitLab, or any shared
repository).

This makes a shared bibliography work exactly like shared code: every change is
reviewable, every version is recoverable, and no one needs an account with a
third-party service.

## Why a plain `.bib` file is ideal for teams

- **Reviewable** — every addition or edit shows up as a readable line-by-line
  diff. You can see who added a reference and why.
- **Mergeable** — two people can add references at the same time and Git merges
  them, just like code.
- **Recoverable** — the full history is in version control. Nothing is ever lost
  to a bad sync.
- **No lock-in, no accounts** — the data is yours, in an open format, forever.

## Set up a shared library with Git

A research group typically keeps one repository for the group bibliography.

=== "Create the shared repo"

    ```bash
    mkdir group-references && cd group-references
    git init
    cp /path/to/your.bib references.bib
    git add references.bib
    git commit -m "Initial group bibliography"
    # push to GitHub / GitLab and add your collaborators
    git remote add origin git@github.com:your-group/group-references.git
    git push -u origin main
    ```

=== "Join an existing repo"

    ```bash
    git clone git@github.com:your-group/group-references.git
    cd group-references
    bibtui references.bib
    ```

## The everyday workflow

1. **Pull** the latest references before you start:

    ```bash
    git pull
    ```

2. **Work in bibtui** — add papers by [DOI](guide/importing.md), tag them with
   [keywords](guide/keywords.md), fetch [PDFs](guide/pdfs.md). Save with
   <kbd>w</kbd>.

3. **Review and commit** your changes:

    ```bash
    git diff references.bib      # see exactly what changed
    git add references.bib
    git commit -m "Add three papers on subglacial hydrology"
    git push
    ```

Because bibtui writes **minimal diffs** — untouched entries stay byte-for-byte
identical — your commits show only what you actually changed, keeping reviews
clean and merges painless.

!!! tip "Use pull requests for curation"

    For a closely-curated reading list, have contributors open a **pull request**
    for new references. The group can discuss a paper's relevance right on the
    diff before it's merged — turning your bibliography into a shared, reviewed
    knowledge base.

## Sharing the PDFs (optional)

Your `.bib` file stores **relative file names**, not absolute paths, for linked
PDFs. That means the same library works on every teammate's machine — as long as
everyone points bibtui at a PDF directory that contains the files.

You have two good options:

- **A shared folder** — put the PDFs in a synced or networked directory
  (a shared drive, Nextcloud, Dropbox, an HPC project folder…) and have each
  person set that as their **PDF base directory** in
  [settings](configuration.md). When one person fetches a PDF, everyone gets it.
- **Fetch locally** — keep PDFs out of the shared store entirely and let each
  teammate run **Library: Fetch missing PDFs** to download open-access copies on
  their own machine. The links resolve identically because they're relative.

!!! note "Keep PDFs out of Git"

    Commit the `.bib` file, but **don't commit the PDFs** to the same Git
    repository — binary files bloat history quickly. Add your PDF directory to
    `.gitignore` and share the files through a folder instead, or let each
    person fetch them. A simple `.gitignore`:

    ```gitignore
    *.pdf
    pdfs/
    *.bib.bak
    ```

## Works the same over SSH and on clusters

Because bibtui runs entirely in the terminal, the team workflow is identical
whether you're on your laptop or SSH'd into a shared HPC login node. Clone the
repo, run `bibtui references.bib`, and you have the full library — search, tags,
PDF fetching and all — wherever your work happens.
