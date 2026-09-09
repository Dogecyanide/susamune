"""Pack the launcher's plain Markdown guide into bounded, wrapped C strings."""

import argparse
import json
from pathlib import Path
import re
import textwrap

WIDTH = 54


def parse_guide(source):
    topics = []
    title = None
    paragraphs = []
    pending = []

    def paragraph():
        if pending:
            paragraphs.append(" ".join(pending))
            pending.clear()

    def topic():
        paragraph()
        if title is None:
            return
        lines = []
        for text in paragraphs:
            if lines:
                lines.append("")
            prefix = re.match(r"(?:\d+\. |- )", text)
            lines.extend(textwrap.wrap(
                text, WIDTH,
                subsequent_indent=" " * len(prefix[0]) if prefix else "",
                break_long_words=False, break_on_hyphens=False))
        if not lines:
            raise ValueError(f"Empty guide topic: {title}")
        if len(title) > 42 or any(len(line) > WIDTH for line in lines):
            raise ValueError(f"Guide text exceeds its display width: {title}")
        topics.append((title, lines))
        paragraphs.clear()

    for line in source.splitlines():
        if any(ord(char) < 32 or ord(char) > 126 for char in line):
            raise ValueError("Launcher guide currently requires printable ASCII")
        if line.startswith("## "):
            topic()
            title = line[3:].strip()
        elif line.startswith("# "):
            if title is not None:
                raise ValueError("Guide title must precede all topics")
        elif not line.strip():
            paragraph()
        elif title is None:
            raise ValueError("Guide prose must belong to a topic")
        else:
            pending.append(line.strip())
    topic()
    if not topics or len(topics) > 255:
        raise ValueError("Guide must have 1 to 255 topics")
    return topics


def generate(source):
    topics = parse_guide(source)
    strings, offsets, entries = [], [], []
    size = 0

    def string(value):
        nonlocal size
        offset = size
        size += len(value) + 1
        strings.append(value)
        return offset

    for title, lines in topics:
        title_offset = string(title)
        entries.append((title_offset, len(offsets), len(lines)))
        offsets.extend(string(line) for line in lines)
    if size > 65535 or len(offsets) > 65535:
        raise ValueError("Guide exceeds its 16-bit string/line offset budget")

    output = ["/* Generated from foxtrot-launcher-guide-en.md. */",
              "static const char kGuideText[] ="]
    output.extend(f"    {json.dumps(value + chr(0))}".replace("\\u0000", "\\0")
                  for value in strings)
    output[-1] += ";"
    output.append("static const unsigned short kGuideLines[] = {")
    for start in range(0, len(offsets), 12):
        output.append("    " + ", ".join(map(str, offsets[start:start + 12])) + ",")
    output.extend(("};", "static const GuideTopic kGuideTopics[] = {"))
    output.extend("    {%d, %d, %d}," % entry for entry in entries)
    output.extend(("};", ""))
    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    content = generate(args.source.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not args.output.exists() or args.output.read_text(encoding="ascii") != content:
        args.output.write_text(content, encoding="ascii")


if __name__ == "__main__":
    main()
