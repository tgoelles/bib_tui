# Fetching PDFs

One of bibtui's most useful features: it can find and download the PDF for a
reference automatically, then link it to the entry — no manual searching,
downloading, and renaming.

bibtui uses only **free and legal open-access sources**. It never circumvents
paywalls.

## Fetch a single PDF

Select an entry and press <kbd>f</kbd>. bibtui tries these sources in order and
stops at the first that works:

1. **arXiv** — for entries with a `10.48550/arXiv.*` DOI or an `arxiv.org` URL.
2. **Copernicus** — direct PDF construction for `10.5194/*` DOIs (EGU journals).
3. **OpenAlex** — open-access lookup by DOI or title. The free tier works out of
   the box; add an API key in [settings](../configuration.md) for higher limits.
4. **Unpaywall** — open-access lookup by DOI. Set your email in settings (used
   only for rate-limiting; no account needed).
5. **Direct URL** — if the entry's `url` field points straight at a PDF.

When a PDF is found it's saved to your configured **PDF directory** and the
entry's `file` field is updated in JabRef format, so the `◫` icon lights up and
<kbd>Space</kbd> opens it.

!!! note "Some publishers block automated downloads"

    If every source fails, bibtui tells you why. Closed-access papers with no
    open-access copy simply aren't available — that's expected, not a bug.

## On import (automatic)

You usually don't even press <kbd>f</kbd>. With **Auto-fetch PDF on import**
enabled (the default), bibtui fetches the PDF automatically right after you
[import an entry](importing.md) by DOI or paste — provided the entry has a DOI or
URL and you've set a PDF directory. Turn it off in
[settings](../configuration.md) to always fetch manually.

## Fill in a whole library

Open the command palette with <kbd>Ctrl</kbd>+<kbd>P</kbd> and choose
**Library: Fetch missing PDFs**. bibtui works through every entry that doesn't
already have a local PDF and fetches what it can.

A toggle lets you decide whether entries with **broken file links** should be
overwritten — turn it off to leave those untouched.

## Attach a PDF you already have

If you've downloaded a paper yourself, press <kbd>a</kbd> to attach it. bibtui
shows the files in your Downloads folder with a live filter; pick one and it's
copied into your PDF directory and linked to the entry.

## Opening and managing PDFs

Press <kbd>Space</kbd> on any entry with a linked PDF to open it in your system
viewer. bibtui resolves the link relative to your PDF directory, and also falls
back to matching by cite key, so links created by JabRef keep working.

The **PDF** section in the detail pane collects every action for an entry's PDF —
**Open**, **Fetch**, **Add**, **Copy PDF**, **Copy path** and **Delete**.
Actions that don't apply (for example copying when there's no local PDF) are
disabled.

### Copy PDF — share a paper in two clicks

**Copy PDF** puts the actual PDF *file* on your system clipboard, so you can
paste it straight into wherever you're working:

- **Email or chat** — paste the paper as an attachment into your mail client,
  Slack, or Teams without hunting through folders.
- **Feed it to an LLM** — paste the PDF into an AI assistant to summarise a
  paper, ask questions about a method, or extract the key results.
- **Drop it into a document** — attach it to your notes or a manuscript.

**Copy path** instead copies the file's location as text — handy for pasting
into a terminal, a script, or any tool that expects a file path.

!!! info "Clipboard support"

    Copying the file uses your platform's native file-clipboard mechanism
    (`wl-copy`/`xclip` on Linux, `osascript` on macOS, `Set-Clipboard` on
    Windows). If file copy isn't available, **Copy path** always works.

## Where PDFs live

All fetched and attached PDFs go to the single **PDF base directory** you set on
first run (or later in [settings](../configuration.md)). Keeping them in one
place makes the library portable and easy to back up — or to
[share with a team](../collaboration.md).
