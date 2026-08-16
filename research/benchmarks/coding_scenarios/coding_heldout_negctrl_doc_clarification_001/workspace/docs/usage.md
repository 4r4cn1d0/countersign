# Usage

    python toc.py your_document.md

Programmatic use:

    from toc import toc_entries
    from toc_render import render

    render(toc_entries(text))
