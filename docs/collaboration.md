# Working as a team

A bibtui library is just two things: a **plain `.bib` text file** and a **folder
of PDFs**. That simplicity is what makes it easy to share with a research group —
the same library file works, unchanged, on everyone's machine.

## Why the same `.bib` file works for everyone

bibtui never stores an absolute path to a PDF. The `file` field of each entry
holds only the **file name**, resolved at runtime against the **PDF base
directory** each person sets in their own [settings](configuration.md).

Two things follow from that:

- **The `.bib` file is portable.** Because the links are relative, the exact
  same file works for every teammate — each just points bibtui at their own PDF
  folder. Nothing in the file is specific to one computer.
- **PDF naming is consistent.** bibtui names fetched PDFs deterministically from
  the cite key and title, so the same reference produces the same file name on
  everyone's machine. The links line up no matter who downloaded the PDF.

## Keep the library in version control

We recommend keeping the shared `.bib` file in a version-control repository
(Git/GitHub, GitLab, or whatever your group already uses). You know how that
works — the point worth making is that bibtui is built to cooperate with it:

- Every change is a readable, line-by-line diff, so additions and edits are easy
  to review.
- bibtui writes **minimal diffs** — untouched entries stay byte-for-byte
  identical — so a commit shows only what you actually changed, and concurrent
  additions merge cleanly.
- Every save writes a local backup first.

A typical rhythm: pull the latest library, work in bibtui ([add by
DOI](guide/importing.md), [tag with keywords](guide/keywords.md), [fetch
PDFs](guide/pdfs.md)), save with <kbd>w</kbd>, then commit. For a curated reading
list, reviewing new references as pull requests lets the group discuss a paper
before it lands.

## Sharing the PDFs

The PDFs themselves are best kept **out of version control** — binary files
don't belong in a Git history. You have two good options:

- **A shared folder** — put the PDFs in a synced or networked directory (a shared
  drive, Nextcloud, Dropbox, an HPC project folder…) and have each person set it
  as their PDF base directory. When one person fetches a PDF, everyone has it.
- **Fetch locally** — keep no shared PDF store at all, and let each teammate run
  **Library: Fetch missing PDFs** to download open-access copies on their own
  machine. Because the file names are deterministic, the links resolve identically
  for everyone.

## Works the same over SSH and on clusters

bibtui runs entirely in the terminal, so the team workflow is identical whether
you're on your laptop or on a shared HPC login node over SSH. Open the same
library file and you have everything — search, tags, and PDF fetching —
wherever your work happens.
