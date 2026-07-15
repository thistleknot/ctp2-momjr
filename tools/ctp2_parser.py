# CTP2 File Parser Framework

import re
from pathlib import Path
from typing import Dict, List, Optional


class CTP2BlockFile:
    """Block { ... } files — uniticon, Wonder, Improve, Advance."""
    re_start = re.compile(r'^(\w[\w_]*)\s*\{')

    def __init__(self):
        self.blocks: Dict[str, Dict[str, str]] = {}

    def parse(self, text: str) -> List[str]:
        warnings = []
        lines = text.split('\n')
        i = 0
        while i < len(lines):
            m = self.re_start.match(lines[i])
            if not m:
                i += 1
                continue
            ident = m.group(1)
            fields = {}
            line = lines[i]
            bs = line.find('{')
            be = line.find('}')
            if be > bs + 1:
                rest = line[bs + 1:be]
                i += 1
            else:
                rest = ''
                i += 1
                while i < len(lines):
                    if '}' in lines[i]:
                        i += 1
                        break
                    if rest:
                        rest += ' '
                    rest += lines[i].strip()
                    i += 1
            # Tokenize rest into key-value pairs
            tokens = []
            j = 0
            while j < len(rest):
                if rest[j] in ' \t\n':
                    j += 1
                    continue
                if rest[j] == '"':
                    end = rest.index('"', j + 1) + 1
                    tokens.append(rest[j:end])  # preserve surrounding quotes
                    j = end
                else:
                    end = j + 1
                    while end < len(rest) and rest[end] not in ' \t\n':
                        end += 1
                    tokens.append(rest[j:end])
                    j = end
            for k in range(0, len(tokens) - 1, 2):
                key = tokens[k]
                val = tokens[k + 1]
                if key and val and key != '}' and val != '}':
                    fields[key] = val
            self.blocks[ident] = fields
        return warnings

    def render(self) -> str:
        lines_out = []
        for ident, fields in self.blocks.items():
            parts = ' '.join(f'{k} {v}' for k, v in fields.items())
            lines_out.append(f'{ident} {{ {parts} }}')
        return '\n'.join(lines_out)


class CountedIconFile:
    """CTP2 counted-icon files: wondericon, improveicon, advanceicon.

    Format: line 1 = integer count, lines 2..N+1 = tab-separated entries.
    Used primarily for CSV export; not used for unit data.
    """

    def __init__(self):
        self.entries: List[str] = []

    def parse(self, text: str) -> List[str]:
        warnings = []
        lines = text.split('\n')
        if not lines:
            return warnings
        first = lines[0].strip().lstrip('#').strip()
        try:
            count = int(first)
        except ValueError:
            self.entries = [l for l in lines[1:] if l.strip() and not l.strip().startswith('#')]
            return warnings
        self.entries = lines[1:count + 1]
        return warnings

    def render(self) -> str:
        return str(len(self.entries)) + '\n' + '\n'.join(self.entries)

    def has_icon(self, icon_id: str) -> bool:
        return any(icon_id in e for e in self.entries)


class FlatListFile:
    def __init__(self):
        self.entries: Dict[str, str] = {}
        self._raw_lines: Dict[str, str] = {}

    def parse(self, text: str):
        for line in text.split('\n'):
            s = line.strip()
            if not s or s.startswith('#'):
                continue
            parts = s.split(None, 1)
            self.entries[parts[0]] = parts[1] if len(parts) > 1 else ""
            self._raw_lines[parts[0]] = line

    def render(self) -> str:
        return '\n'.join(self._raw_lines.get(k, f"{k} {v}") for k, v in self.entries.items())


class RawBlockTextFile:
    """
    Multi-line CTP2 block file that preserves block text verbatim.

    Supports safe block removal and bare-flag insertion for database files whose
    format cannot be round-tripped through the simple key/value tokenizer.
    """

    re_block_id = re.compile(r'^([A-Z][A-Z0-9_]+)\s*\{', re.MULTILINE)

    def __init__(self):
        self._text: str = ""
        self.blocks: Dict[str, str] = {}

    def _scan_blocks(self, text: str):
        lines = text.splitlines(keepends=True)
        prefix = []
        blocks = []
        i = 0
        seen_first_block = False
        while i < len(lines):
            line = lines[i]
            match = self.re_block_id.match(line)
            if not match:
                if not seen_first_block:
                    prefix.append(line)
                i += 1
                continue
            seen_first_block = True
            ident = match.group(1)
            block_lines = [line]
            depth = line.count('{') - line.count('}')
            i += 1
            while i < len(lines) and depth > 0:
                block_lines.append(lines[i])
                depth += lines[i].count('{') - lines[i].count('}')
                i += 1
            blocks.append((ident, ''.join(block_lines).rstrip('\n')))
        return ''.join(prefix), blocks

    def _rebuild_text(self, prefix: str, blocks) -> str:
        body = "\n\n".join(block for _, block in blocks)
        if prefix and body:
            return prefix.rstrip('\n') + "\n\n" + body + "\n"
        if body:
            return body + "\n"
        return prefix

    def _replace_blocks(self, blocks) -> None:
        prefix, _ = self._scan_blocks(self._text)
        self._text = self._rebuild_text(prefix, blocks)
        self.blocks = {ident: block for ident, block in blocks}

    def parse(self, text: str) -> List[str]:
        self._text = text
        prefix, blocks = self._scan_blocks(text)
        deduped = []
        seen = set()
        for ident, block in reversed(blocks):
            if ident in seen:
                continue
            seen.add(ident)
            deduped.append((ident, block))
        deduped.reverse()
        if len(deduped) != len(blocks):
            self._text = self._rebuild_text(prefix, deduped)
        self.blocks = {ident: block for ident, block in deduped}
        return []

    def add_block(self, ident: str, block_text: str) -> None:
        blocks = list(self.blocks.items())
        replaced = False
        for index, (block_id, _) in enumerate(blocks):
            if block_id == ident:
                blocks[index] = (ident, block_text.rstrip('\n'))
                replaced = True
                break
        if not replaced:
            blocks.append((ident, block_text.rstrip('\n')))
        self._replace_blocks(blocks)

    def remove_block(self, ident: str) -> bool:
        if ident not in self.blocks:
            return False
        blocks = [(block_id, block_text) for block_id, block_text in self.blocks.items() if block_id != ident]
        self._replace_blocks(blocks)
        return True

    def ensure_flags(self, ident: str, flags: List[str]) -> bool:
        block_text = self.blocks.get(ident)
        if not block_text:
            return False
        missing_flags = [
            flag
            for flag in flags
            if not re.search(rf'^\s*{re.escape(flag)}\s*$', block_text, re.MULTILINE)
        ]
        if not missing_flags:
            return False
        lines = block_text.splitlines(keepends=True)
        if not lines:
            return False
        closing_index = None
        for index in range(len(lines) - 1, -1, -1):
            if lines[index].strip() == '}':
                closing_index = index
                break
        if closing_index is None:
            return False
        insert_lines = [f"   {flag}\n" for flag in missing_flags]
        lines[closing_index:closing_index] = insert_lines
        self.add_block(ident, ''.join(lines))
        return True

    def render(self) -> str:
        return self._text


class LibraryFile:
    def __init__(self):
        self.sections: Dict[str, str] = {}

    def parse(self, text: str):
        # MoM carries legacy GL transitions in the form "[END][NEXT_SECTION]".
        # Normalize them before parsing so round-trips do not merge entire
        # section families into the preceding block.
        text = re.sub(r'\[END\]\[([\w_]+)\]', r'[END]\n[\1]', text)
        current = None
        content = []
        for line in text.split('\n'):
            m = re.match(r'^\[([\w_]+)\]$', line.strip())
            if m:
                if current:
                    self.sections[current] = '\n'.join(content).strip()
                current = m.group(1)
                content = []
            elif line.strip() == '[END]':
                if current:
                    self.sections[current] = '\n'.join(content).strip()
                current = None
                content = []
            elif current:
                content.append(line)
        if current:
            self.sections[current] = '\n'.join(content).strip()

    def render(self) -> str:
        lines = []
        for section_id, content in self.sections.items():
            lines.append(f'[{section_id}]')
            if content:
                lines.append(content)
            lines.append('[END]')
        return '\n'.join(lines)


class StringDBFile:
    def __init__(self):
        self.entries: Dict[str, str] = {}

    def parse(self, text: str):
        for line in text.split('\n'):
            s = line.strip()
            if not s or s.startswith('#'):
                continue
            if '\t' in s:
                key, val = s.split('\t', 1)
                self.entries[key] = val.strip().strip('"')

    def render(self) -> str:
        lines = []
        for key, val in self.entries.items():
            # Column-align value to col 48 using 8-char tab stops (matches base game gl_str.txt)
            cur = len(key)
            tabs = 0
            while cur < 48:
                cur = ((cur // 8) + 1) * 8
                tabs += 1
            if tabs < 1:
                tabs = 1
            lines.append(f'{key}{chr(9) * tabs}"{val}"')
        return '\n'.join(lines)


class UnitsFile:
    """CTP2 Units.txt — complex multi-line format with nested sub-blocks and bare flags.

    Preserves the file content verbatim. New unit blocks are appended only;
    existing units are never re-rendered, preventing format corruption.
    """

    re_unit_id = re.compile(r'^(UNIT_\w+)\s*\{', re.MULTILINE)

    def __init__(self):
        self._text: str = ""
        self._unit_ids: set = set()

    def parse(self, text: str) -> List[str]:
        self._text = text
        for m in self.re_unit_id.finditer(text):
            self._unit_ids.add(m.group(1))
        return []

    def has_unit(self, ident: str) -> bool:
        return ident in self._unit_ids

    def add_unit(self, ident: str, block_text: str):
        """Append a fully-formed unit block if ident is not already present."""
        if ident not in self._unit_ids:
            self._unit_ids.add(ident)
            self._text = self._text.rstrip('\n') + "\n\n" + block_text + "\n"

    def ensure_flags(self, ident: str, flags: List[str]) -> bool:
        """
        Insert bare unit flags into an existing Units.txt block.

        Require: ident is a unit ID and flags are bare CTP2 flag names.
        Guarantee: returns True only when text changed; preserves existing block
        formatting and nested sub-blocks. Missing units are left unchanged.
        Failure modes: malformed unclosed unit blocks are ignored.
        """
        match = re.search(rf'^{re.escape(ident)}\s*\{{', self._text, re.MULTILINE)
        if not match:
            return False

        line_start = self._text.rfind('\n', 0, match.start()) + 1
        lines = self._text[line_start:].splitlines(keepends=True)
        depth = 0
        block_end_index = None
        block_lines = []

        for index, line in enumerate(lines):
            depth += line.count('{') - line.count('}')
            block_lines.append(line)
            if index > 0 and depth <= 0:
                block_end_index = index
                break

        if block_end_index is None:
            return False

        block_text = ''.join(block_lines)
        missing_flags = [
            flag
            for flag in flags
            if not re.search(rf'^\s*{re.escape(flag)}\s*$', block_text, re.MULTILINE)
        ]
        if not missing_flags:
            return False

        closing_line = block_lines[block_end_index]
        insert_lines = [f"   {flag}\n" for flag in missing_flags]
        block_lines[block_end_index:block_end_index] = insert_lines
        new_block = ''.join(block_lines)

        block_start = line_start
        block_end = line_start + len(block_text)
        self._text = self._text[:block_start] + new_block + self._text[block_end:]
        return True

    def remove_unit(self, ident: str) -> bool:
        """
        Remove a complete unit block (including nested sub-blocks) from the text.

        Require: ident is a UNIT_* identifier present in the file.
        Guarantee: returns True if found and removed; False otherwise.
          All other blocks and surrounding whitespace are preserved intact.
        Failure modes: malformed unclosed blocks are left untouched.
        """
        match = re.search(rf'^{re.escape(ident)}\s*\{{', self._text, re.MULTILINE)
        if not match:
            return False

        line_start = self._text.rfind('\n', 0, match.start()) + 1
        lines = self._text[line_start:].splitlines(keepends=True)
        depth = 0
        block_end_index = None

        for index, line in enumerate(lines):
            depth += line.count('{') - line.count('}')
            if index > 0 and depth <= 0:
                block_end_index = index
                break

        if block_end_index is None:
            return False

        block_text = ''.join(lines[:block_end_index + 1])
        block_start = line_start
        block_end = line_start + len(block_text)
        tail = self._text[block_end:]
        if tail.startswith('\n'):
            tail = tail[1:]
        self._text = self._text[:block_start] + tail
        self._unit_ids.discard(ident)
        return True

    def render(self) -> str:
        return self._text

class AdvanceFile:
    """CTP2 Advance.txt — multi-line format with bare boolean flags.

    Preserves the file content verbatim. New advance blocks are appended only;
    existing advances are never re-rendered, preventing tokenizer corruption
    of boolean flags like 'Infrastructure' and 'Tunnels'.
    The 'blocks' attribute is a dict keyed by advance ID (values are empty
    dicts) so existing code using 'ident in adv.blocks' still works.
    """

    re_adv_id = re.compile(r'^(ADVANCE_\w+)\s*\{', re.MULTILINE)

    def __init__(self):
        self._text: str = ""
        self.blocks: Dict[str, dict] = {}  # id → {} for membership testing

    def _scan_blocks(self, text: str):
        """Return (prefix, [(ident, block_text), ...]) for raw Advance.txt content.

        Purpose:
            Preserve each advance block verbatim while still letting us reconcile
            duplicate IDs at parse time.

        Preconditions:
            ``text`` is the full Advance.txt payload.

        Failure modes:
            If a block is malformed and never closes, the remainder of the file is
            treated as part of that block.
        """
        lines = text.splitlines(keepends=True)
        prefix = []
        blocks = []
        i = 0
        seen_first_block = False
        while i < len(lines):
            line = lines[i]
            m = self.re_adv_id.match(line)
            if not m:
                if not seen_first_block:
                    prefix.append(line)
                i += 1
                continue
            seen_first_block = True
            ident = m.group(1)
            block_lines = [line]
            depth = line.count('{') - line.count('}')
            i += 1
            while i < len(lines) and depth > 0:
                block_lines.append(lines[i])
                depth += lines[i].count('{') - lines[i].count('}')
                i += 1
            blocks.append((ident, ''.join(block_lines).rstrip('\n')))
        return ''.join(prefix), blocks

    def _rebuild_text(self, prefix: str, blocks) -> str:
        body = "\n\n".join(block for _, block in blocks)
        if prefix and body:
            return prefix.rstrip('\n') + "\n\n" + body + "\n"
        if body:
            return body + "\n"
        return prefix

    def parse(self, text: str) -> List[str]:
        self.blocks = {}
        prefix, blocks = self._scan_blocks(text)
        deduped = []
        seen = set()
        for ident, block in reversed(blocks):
            if ident in seen:
                continue
            seen.add(ident)
            deduped.append((ident, block))
        deduped.reverse()
        self._text = self._rebuild_text(prefix, deduped) if len(deduped) != len(blocks) else text
        for ident, _ in deduped:
            self.blocks[ident] = {}
        return []

    def add_advance(self, ident: str, block_text: str):
        """Append block_text if ident is not already present."""
        if ident not in self.blocks:
            self.blocks[ident] = {}
            self._text = self._text.rstrip('\n') + "\n\n" + block_text + "\n"

    def ensure_flags(self, ident: str, flags: List[str]) -> bool:
        """
        Insert bare advance flags into an existing Advance.txt block.

        Require: ``ident`` is an advance ID and ``flags`` are bare CTP2 flag
        names already supported by Advance.txt.
        Guarantee: returns True only when text changed; preserves existing block
        text other than inserting the missing flags before the closing brace.
        Failure modes: missing or malformed blocks are left unchanged.
        """
        match = re.search(rf'^{re.escape(ident)}\s*\{{', self._text, re.MULTILINE)
        if not match:
            return False

        line_start = self._text.rfind('\n', 0, match.start()) + 1
        lines = self._text[line_start:].splitlines(keepends=True)
        depth = 0
        block_end_index = None
        block_lines = []

        for index, line in enumerate(lines):
            depth += line.count('{') - line.count('}')
            block_lines.append(line)
            if index > 0 and depth <= 0:
                block_end_index = index
                break

        if block_end_index is None:
            return False

        block_text = ''.join(block_lines)
        missing_flags = [
            flag
            for flag in flags
            if not re.search(rf'^\s*{re.escape(flag)}\s*$', block_text, re.MULTILINE)
        ]
        if not missing_flags:
            return False

        insert_lines = [f"   {flag}\n" for flag in missing_flags]
        block_lines[block_end_index:block_end_index] = insert_lines
        new_block = ''.join(block_lines)

        block_start = line_start
        block_end = line_start + len(block_text)
        self._text = self._text[:block_start] + new_block + self._text[block_end:]
        return True

    def _locate_block(self, ident: str):
        """Return (block_start, block_end, block_lines, close_index) for ident.

        block_start/block_end are absolute offsets into ``self._text``; block_lines
        is the list of keepends lines from the opening line through (and including)
        the closing-brace line at index ``close_index``. Returns None when the block
        is missing or never closes. Mirrors the span logic in ``ensure_flags``.
        """
        match = re.search(rf'^{re.escape(ident)}\s*\{{', self._text, re.MULTILINE)
        if not match:
            return None
        line_start = self._text.rfind('\n', 0, match.start()) + 1
        lines = self._text[line_start:].splitlines(keepends=True)
        depth = 0
        block_lines = []
        for index, line in enumerate(lines):
            depth += line.count('{') - line.count('}')
            block_lines.append(line)
            if index > 0 and depth <= 0:
                block_end = line_start + len(''.join(block_lines))
                return line_start, block_end, block_lines, index
        return None

    def get_prerequisites(self, ident: str) -> List[str]:
        """Return the ADVANCE_* ids on this advance's ``Prerequisites`` lines."""
        located = self._locate_block(ident)
        if located is None:
            return []
        _, _, block_lines, _ = located
        prereqs: List[str] = []
        for line in block_lines:
            m = re.match(r'^\s*Prerequisites\s+(ADVANCE_\w+)\s*$', line)
            if m:
                prereqs.append(m.group(1))
        return prereqs

    def remove_prerequisites(self, ident: str, advances: List[str]) -> bool:
        """Delete ``Prerequisites <adv>`` lines whose advance is in ``advances``.

        Require: ``ident`` is an advance ID. Guarantee: returns True only when at
        least one prerequisite line was removed; other block text is preserved
        verbatim. Failure modes: missing/malformed blocks are left unchanged.
        """
        located = self._locate_block(ident)
        if located is None:
            return False
        block_start, block_end, block_lines, _ = located
        drop = set(advances)
        kept_lines = []
        removed = False
        for line in block_lines:
            m = re.match(r'^\s*Prerequisites\s+(ADVANCE_\w+)\s*$', line)
            if m and m.group(1) in drop:
                removed = True
                continue
            kept_lines.append(line)
        if not removed:
            return False
        self._text = self._text[:block_start] + ''.join(kept_lines) + self._text[block_end:]
        return True

    def ensure_self_prerequisite(self, ident: str) -> bool:
        """Insert ``Prerequisites <ident>`` so the advance can never be researched.

        The CTP2 engine (Advances.cpp::ResetCanResearch) forces canResearch=FALSE
        for any advance that lists itself as a prerequisite, while the block stays
        in the Advance DB so every reference to it still resolves. Guarantee:
        returns True only when the self-prerequisite was newly inserted before the
        closing brace. Failure modes: missing/malformed blocks are left unchanged.
        """
        located = self._locate_block(ident)
        if located is None:
            return False
        block_start, block_end, block_lines, close_index = located
        block_text = ''.join(block_lines)
        if re.search(rf'^\s*Prerequisites\s+{re.escape(ident)}\s*$', block_text, re.MULTILINE):
            return False
        block_lines[close_index:close_index] = [f"   Prerequisites {ident}\n"]
        self._text = self._text[:block_start] + ''.join(block_lines) + self._text[block_end:]
        return True

    def render(self) -> str:
        return self._text


class WonderFile:
    """CTP2 Wonder.txt — multi-line format with bare boolean flags.

    Preserves the file content verbatim. New wonder blocks are appended only;
    existing wonders are never re-rendered, preventing tokenizer corruption
    of bare flags like 'FreeSlaves', 'ProhibitSlavers', 'PreventConversion'.
    The 'blocks' attribute is a dict keyed by wonder ID so that
    'ident in won.blocks' works without modification to callers.
    """

    re_wonder_id = re.compile(r'^(WONDER_\w+)\s*\{', re.MULTILINE)

    def __init__(self):
        self._text: str = ""
        self.blocks: Dict[str, dict] = {}

    def parse(self, text: str) -> List[str]:
        self._text = text
        for m in self.re_wonder_id.finditer(text):
            self.blocks[m.group(1)] = {}
        return []

    def add_wonder(self, ident: str, block_text: str):
        """Append block_text if ident is not already present."""
        if ident not in self.blocks:
            self.blocks[ident] = {}
            self._text = self._text.rstrip('\n') + "\n\n" + block_text + "\n"

    def ensure_flags(self, ident: str, flags: List[str]) -> bool:
        """
        Insert bare wonder flags into an existing Wonder.txt block.

        Require: ``ident`` is a wonder ID and ``flags`` are bare CTP2 flag
        names already supported by Wonder.txt.
        Guarantee: returns True only when text changed; preserves existing block
        text other than inserting missing flags before the closing brace.
        Failure modes: missing or malformed blocks are left unchanged.
        """
        match = re.search(rf'^{re.escape(ident)}\s*\{{', self._text, re.MULTILINE)
        if not match:
            return False

        line_start = self._text.rfind('\n', 0, match.start()) + 1
        lines = self._text[line_start:].splitlines(keepends=True)
        depth = 0
        block_end_index = None
        block_lines = []

        for index, line in enumerate(lines):
            depth += line.count('{') - line.count('}')
            block_lines.append(line)
            if index > 0 and depth <= 0:
                block_end_index = index
                break

        if block_end_index is None:
            return False

        block_text = ''.join(block_lines)
        missing_flags = [
            flag
            for flag in flags
            if not re.search(rf'^\s*{re.escape(flag)}\s*$', block_text, re.MULTILINE)
        ]
        if not missing_flags:
            return False

        insert_lines = [f"   {flag}\n" for flag in missing_flags]
        block_lines[block_end_index:block_end_index] = insert_lines
        new_block = ''.join(block_lines)

        block_start = line_start
        block_end = line_start + len(block_text)
        self._text = self._text[:block_start] + new_block + self._text[block_end:]
        return True

    def render(self) -> str:
        return self._text


PARSER_MAP = {
    "default/gamedata/Wonder.txt": WonderFile,
    "default/gamedata/Improve.txt": CTP2BlockFile,
    "default/gamedata/Advance.txt": AdvanceFile,
    "default/gamedata/Units.txt": UnitsFile,
    # Backup unit files — same block format as Units.txt; must also receive
    # unit_mask.csv removals so the engine never loads a stale UNIT_* that
    # was removed from Units.txt (causes "X not found in Unit database").
    "default/gamedata/Units_historic.txt": UnitsFile,
    "default/gamedata/Units_release.txt": UnitsFile,
    "default/gamedata/tileimp.txt": CTP2BlockFile,
    "default/gamedata/uniticon.txt": CTP2BlockFile,
    "default/gamedata/wondericon.txt": CountedIconFile,
    "default/gamedata/improveicon.txt": CountedIconFile,
    "default/gamedata/advanceicon.txt": CountedIconFile,
    "english/gamedata/gl_str.txt": StringDBFile,
    "english/gamedata/Great_Library.txt": LibraryFile,
}


class FileRegistry:
    """Holds parsed content for all files. Loads on demand. Saves all."""
    def __init__(self, scenario: Path, ctp2_data: Path = None):
        self.scenario = scenario
        self.ctp2_data = ctp2_data or Path(r"H:\Program Files(x86)\Activision\Call To Power 2\ctp2_data")
        self._parsed: Dict[str, object] = {}

    def _find(self, rel: str) -> Path:
        p = self.scenario / rel
        if p.exists():
            return p
        p = self.ctp2_data / rel
        if p.exists():
            return p
        return None

    def load(self, rel: str):
        if rel in self._parsed:
            return self._parsed[rel]
        cls = PARSER_MAP[rel]
        p = self._find(rel)
        text = p.read_text(encoding='latin-1') if p and p.exists() else ""
        obj = cls()
        obj.parse(text)
        self._parsed[rel] = obj
        return obj

    def text(self, rel: str) -> str:
        p = self._find(rel)
        return p.read_text(encoding='latin-1') if p else ""

    def save(self, rel: str):
        obj = self._parsed.get(rel)
        if obj and hasattr(obj, 'render'):
            p = self.scenario / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            rendered = obj.render()
            # CTP2 engine expects at least one trailing blank line at EOF for block files.
            # Base game files typically end with \n\n\n. Ensure we have at least \n\n.
            if not rendered.endswith('\n\n'):
                rendered += '\n\n'
            # Use newline='' to write LF-only (matching CTP2 base game file format).
            # Default text mode on Windows produces CRLF, which causes the CTP2 engine
            # to leave \r on keys/values, breaking string lookups → blank GL list items.
            with p.open('w', encoding='latin-1', newline='') as fh:
                fh.write(rendered)

    def save_all(self):
        for rel in list(self._parsed.keys()):
            self.save(rel)


# === ENTITY REGISTRATION — one entity = multiple files ===

def _unpack_module_docstring(mod):
    """Parse module existence helper """
    return True

class EntityRegistry:
    """Registry of CTP2 mod entities. Each entity tracks its footprint."""

    def __init__(self):
        self.advances = []
        self.wonders = []
        self.buildings = []
        self.units = []
        self.tileimps = []

    def add_advance(self, advance):
        self.advances.append(advance)
        return advance

    def add_wonder(self, wonder):
        self.wonders.append(wonder)
        return wonder

    def add_building(self, building):
        self.buildings.append(building)
        return building

    def add_tileimp(self, tileimp):
        self.tileimps.append(tileimp)
        return tileimp

    def register_all(self, reg: FileRegistry):
        for entity in self.advances + self.units + self.wonders + self.buildings + self.tileimps:
            entity.register(reg)


class ModAdvance:
    def __init__(self, ident: str, name: str, cost: str, branch: str, age: str,
                 icon: str = "", prereqs: list = None, desc: str = ""):
        self.ident = ident
        self.name = name
        self.cost = cost
        self.branch = branch
        self.age = age
        self.icon = icon or f"ICON_{ident}"
        self.prereqs = prereqs or []
        self.desc = desc

    def _block_text(self) -> str:
        """Return a fully-formed multi-line advance block."""
        # Strip any trailing ; comment from branch — CTP2 uses # not ;
        branch = str(self.branch).split(';')[0].strip()
        lines = [f"{self.ident} {{"]
        for p in self.prereqs:
            lines.append(f"   Prerequisites {p}")
        lines += [
            f"   Cost {self.cost}",
            f"   Icon {self.icon}",
            f"   Branch {branch}",
            f"   Age {self.age}",
        ]
        lines.append("}")
        return "\n".join(lines)

    def register(self, reg: FileRegistry):
        # Advance.txt — append-only; never re-renders existing content
        adv = reg.load("default/gamedata/Advance.txt")
        adv.add_advance(self.ident, self._block_text())
        # gl_str.txt
        s = reg.load("english/gamedata/gl_str.txt")
        s.entries[self.ident] = self.name
        if self.desc:
            s.entries[f"DESCRIPTION_{self.ident}"] = self.desc
        # Great_Library.txt
        gl = reg.load("english/gamedata/Great_Library.txt")
        for suffix in ["GAMEPLAY", "HISTORICAL"]:
            gl.sections.setdefault(
                f"{self.ident}_{suffix}",
                f"<L:DATABASE_ADVANCES,{self.ident}>{self.name}<e>",
            )
        prereq_section = "Requires:\n"
        for p in self.prereqs:
            prereq_section += f"<L:DATABASE_ADVANCES,{p}>{p.split('_', 1)[1].title() if '_' in p else p}<e>\n"
        if not self.prereqs:
            prereq_section = "Requires:\nNothing"
        gl.sections[f"{self.ident}_PREREQ"] = prereq_section.strip()
        _age_display = {
            'AGE_ONE': 'Ancient', 'AGE_TWO': 'Medieval', 'AGE_THREE': 'Renaissance',
            'AGE_FOUR': 'Industrial', 'AGE_FIVE': 'Modern',
        }
        branch_display = str(self.branch).split(';')[0].strip()
        age_display = _age_display.get(str(self.age).strip(), str(self.age))
        gl.sections[f"{self.ident}_STATISTICS"] = f"Cost: {self.cost}\nAge: {age_display}\nBranch: {branch_display}"
        # uniticon.txt — required or engine raises "not found in Icon database"
        uic = reg.load("default/gamedata/uniticon.txt")
        if self.icon not in uic.blocks:
            uic.blocks[self.icon] = {
                "FirstFrame": '"UPLG001.TGA"',
                "Movie": '"NULL"',
                "Gameplay": f'"{self.ident}_GAMEPLAY"',
                "Historical": f'"{self.ident}_HISTORICAL"',
                "Prereq": f'"{self.ident}_PREREQ"',
                "Vari": f'"{self.ident}_STATISTICS"',
                "Icon": '"UPLG001.TGA"',
                "LargeIcon": '"NULL"',
                "SmallIcon": '"NULL"',
                "StatText": f'"{self.ident}_PREREQ"',
            }

    def check(self, reg: FileRegistry) -> List[str]:
        errors = []
        adv = reg.load("default/gamedata/Advance.txt")
        if self.ident not in adv.blocks:
            errors.append(f"{self.ident} not in Advance.txt")
        uic = reg.load("default/gamedata/uniticon.txt")
        if self.icon not in uic.blocks:
            errors.append(f"{self.icon} not in uniticon.txt")
        return errors


class ModBuilding:
    def __init__(self, ident: str, name: str, cost: str, upkeep: str,
                 advance: str, icon: str = "", desc: str = ""):
        self.ident = ident
        self.name = name
        self.cost = cost
        self.upkeep = upkeep
        self.advance = advance
        self.icon = icon or f"ICON_{ident}"
        self.desc = desc

    def register(self, reg: FileRegistry):
        # Improve.txt — only include ENABLING_ADVANCE when non-empty; an empty
        # value would cause the renderer to produce "ENABLING_ADVANCE " (no rhs)
        # which the CTP2 parser misreads by consuming the NEXT token as the value.
        imp = reg.load("default/gamedata/Improve.txt")
        fields: Dict[str, str] = {
            "IMPROVEMENT_PRODUCTION_COST": self.cost,
            "IMPROVEMENT_UPKEEP": self.upkeep,
            "IMPROVE_DEFAULT_ICON": self.icon,
            "IMPROVE_DESCRIPTION": f"DESCRIPTION_{self.ident}",
        }
        if self.advance:
            fields["ENABLING_ADVANCE"] = self.advance
        imp.blocks[self.ident] = fields
        # uniticon.txt
        uic = reg.load("default/gamedata/uniticon.txt")
        uic.blocks[self.icon] = {
            "FirstFrame": '"UPLG001.TGA"',
            "Movie": '"NULL"',
            "Gameplay": f'"{self.ident}_GAMEPLAY"',
            "Historical": f'"{self.ident}_HISTORICAL"',
            "Prereq": f'"{self.ident}_PREREQ"',
            "Vari": f'"{self.ident}_STATISTICS"',
            "Icon": '"UPLG001.TGA"',
            "LargeIcon": '"NULL"',
            "SmallIcon": '"NULL"',
            "StatText": f'"{self.ident}_STATISTICS"',
        }
        # gl_str.txt
        s = reg.load("english/gamedata/gl_str.txt")
        s.entries[self.ident] = self.name
        s.entries[f"DESCRIPTION_{self.ident}"] = self.desc
        # Great_Library.txt
        gl = reg.load("english/gamedata/Great_Library.txt")
        for suffix in ["GAMEPLAY", "HISTORICAL"]:
            gl.sections[f"{self.ident}_{suffix}"] = f"<L:DATABASE_IMPROVEMENTS,{self.ident}>{self.name}<e>"
        if self.advance:
            prereq_label = self.advance.split('_', 1)[1].title() if '_' in self.advance else self.advance
            gl.sections[f"{self.ident}_PREREQ"] = f"Requires:\n<L:DATABASE_ADVANCES,{self.advance}>{prereq_label}<e>"
        else:
            gl.sections[f"{self.ident}_PREREQ"] = f"No advance required."
        gl.sections[f"{self.ident}_STATISTICS"] = f"<L:DATABASE_IMPROVEMENTS,{self.ident}>{self.name}<e>"

    def check(self, reg : FileRegistry) -> List[str]:
        errors = []
        imp = reg.load("default/gamedata/Improve.txt")
        if self.ident not in imp.blocks:
            errors.append(f"{self.ident} not in Improve.txt")
        # Verify the advance exists
        adv = reg.load("default/gamedata/Advance.txt")
        if self.advance not in adv.blocks:
            errors.append(f"{self.ident} requires {self.advance} which is not in Advance.txt")
        return errors


class ModTileImp:
    """Tile improvement entity — writes to tileimp.txt."""
    def __init__(self, ident: str, name: str, level: str, tile_class: str,
                 icon: str = "", tooltip: str = "", statusbar: str = "",
                 sound: str = "", construction_tiles: str = "",
                 cant_build_on: str = "", excludes: str = "",
                 terrain_effects: List[Dict[str, str]] = None):
        self.ident = ident
        self.name = name
        self.level = level
        self.tile_class = tile_class
        self.icon = icon or f"ICON_{ident}"
        self.tooltip = tooltip
        self.statusbar = statusbar
        self.sound = sound
        self.construction_tiles = construction_tiles
        self.cant_build_on = cant_build_on
        self.excludes = excludes
        self.terrain_effects = terrain_effects or []

    def register(self, reg: FileRegistry):
        """Write this tile improvement to tileimp.txt."""
        tileimp = reg.load("default/gamedata/tileimp.txt")
        block = {
            "Icon": self.icon,
            "Tooltip": self.tooltip or f"TOOLTIP_{self.ident}",
            "Statusbar": self.statusbar or f"STATUSBAR_{self.ident}",
            "Sound": self.sound or "None",
            "Level": self.level,
            "Class": self.tile_class,
            "ConstructionTiles": self.construction_tiles,
            "CantBuildOn": self.cant_build_on,
            "Excludes": self.excludes,
        }
        # Build nested TerrainEffect blocks
        terrain_data = []
        for te in self.terrain_effects:
            te_block = {"Terrain": te.get("terrain", "")}
            for key in ("BonusFood", "BonusProduction", "BonusGold",
                       "EnableAdvance", "ProductionCost", "ProductionTime",
                       "TilesetIndex"):
                if key in te:
                    te_block[key] = te[key]
            terrain_data.append(te_block)

        # Store terrain effects as a sub-dict under TerrainEffects
        # The CTP2BlockFile.render() handles this — check how it serializes
        # If render() doesn't handle nested blocks, we need to store as string
        # Actually, looking at CTP2BlockFile, it stores Dict[str, str] so
        # we may need a different approach for TerrainEffect sub-blocks.

        tileimp.blocks[self.ident] = block
        if terrain_data:
            tileimp.blocks[f"{self.ident}_TERRAIN"] = {"_terrain_effects": terrain_data}

    def check(self, reg: FileRegistry) -> List[str]:
        """Validate this tile improvement exists in tileimp.txt."""
        issues = []
        try:
            tileimp = reg.load("default/gamedata/tileimp.txt")
            if self.ident not in tileimp.blocks:
                issues.append(f"TileImp {self.ident} not found in tileimp.txt")
        except Exception as e:
            issues.append(f"Error loading tileimp.txt: {e}")
        return issues


class ModWonder:
    def __init__(self, ident: str, name: str, cost: str, advance: str,
                 icon: str = "", desc: str = "", movie: str = ""):
        self.ident = ident
        self.name = name
        self.cost = cost
        self.advance = advance
        self.icon = icon or f"ICON_{ident}"
        self.desc = desc
        self.movie = movie

    def _block_text(self) -> str:
        """Return a fully-formed multi-line wonder block."""
        lines = [f"{self.ident} {{"]
        lines.append(f"   DefaultIcon {self.icon}")
        lines.append(f"   Description DESCRIPTION_{self.ident}")
        if self.movie:
            lines.append(f"   Movie MOVIE_{self.ident}")
        lines.append(f"   EnableAdvance {self.advance}")
        lines.append(f"   ProductionCost {self.cost}")
        lines.append("}")
        return "\n".join(lines)

    def register(self, reg: FileRegistry):
        # Wonder.txt — append-only; never re-renders existing content
        won = reg.load("default/gamedata/Wonder.txt")
        won.add_wonder(self.ident, self._block_text())
        # uniticon.txt (wonder icon for icon display)
        uic = reg.load("default/gamedata/uniticon.txt")
        uic.blocks[self.icon] = {
            "FirstFrame": '"UPLG001.TGA"',
            "Movie": '"NULL"',
            "Gameplay": f'"{self.ident}_GAMEPLAY"',
            "Historical": f'"{self.ident}_HISTORICAL"',
            "Prereq": f'"{self.ident}_PREREQ"',
            "Vari": f'"{self.ident}_STATISTICS"',
            "Icon": '"UPLG001.TGA"',
            "LargeIcon": '"NULL"',
            "SmallIcon": '"NULL"',
            "StatText": f'"{self.ident}_STATISTICS"',
        }
        # gl_str.txt
        s = reg.load("english/gamedata/gl_str.txt")
        s.entries[self.ident] = self.name
        s.entries[f"DESCRIPTION_{self.ident}"] = self.desc
        if self.movie:
            s.entries[f"MOVIE_{self.ident}"] = ""
        s.entries[f"{self.ident}_ARTICLE"] = "the "
        # Great_Library.txt
        gl = reg.load("english/gamedata/Great_Library.txt")
        for suffix in ["GAMEPLAY", "HISTORICAL"]:
            gl.sections[f"{self.ident}_{suffix}"] = f"<L:DATABASE_WONDERS,{self.ident}>{self.name}<e>"
        gl.sections[f"{self.ident}_PREREQ"] = f"Requires:\n<L:DATABASE_ADVANCES,{self.advance}>{self.advance.split('_', 1)[1].title() if '_' in self.advance else self.advance}<e>"
        gl.sections[f"{self.ident}_STATISTICS"] = f"<L:DATABASE_WONDERS,{self.ident}>{self.name}<e>"

    def check(self, reg: FileRegistry) -> List[str]:
        errors = []
        won = reg.load("default/gamedata/Wonder.txt")
        if self.ident not in won.blocks:
            errors.append(f"{self.ident} not in Wonder.txt")
        adv = reg.load("default/gamedata/Advance.txt")
        if self.advance not in adv.blocks:
            errors.append(f"{self.ident} requires {self.advance} not in Advance.txt")
        return errors


class ModUnit:
    """A CTP2 unit entity.

    Registers across Units.txt (append-only), uniticon.txt, gl_str.txt,
    and Great_Library.txt. All required CTP2 fields are generated so the
    engine never hits a "missing field" parse error.

    Args:
        ident:        e.g. "UNIT_PEASANTS"
        name:         display name, e.g. "Peasants"
        category:     UNIT_CATEGORY_ATTACK / _NAVAL / _AIR / _SPECIAL
        attack:       CTP2 Attack value (already scaled by caller)
        defense:      CTP2 Defense value (already scaled by caller)
        sprite:       DefaultSprite identifier (REQUIRED by engine)
        icon:         icon override; defaults to ICON_{ident}
        desc:         short description for gl_str / Great Library
        advance:      EnableAdvance identifier, or "" for no prereq
        move:         MaxMovePoints (100 = 1 movement point in MoM)
        hp:           MaxHP
        firepower:    Firepower
        armor:        Armor
        zbrange:      ZBRangeAttack (0 for melee units)
        shield_cost:  ShieldCost
        shield_hunger: ShieldHunger per turn
        gold_hunger:  GoldHunger per turn
        sound_set:    base unit name used for all SOUND_ IDs (e.g. "WARRIOR")
        domain:       0 = land, 1 = air, 2 = sea
        size:         Small / Medium / Large
    """

    def __init__(self, ident: str, name: str, category: str, attack: int, defense: int,
                 sprite: str = "SPRITE_WARRIOR", icon: str = "", desc: str = "",
                 advance: str = "", move: int = 100, hp: int = 10, firepower: int = 1,
                 armor: int = 1, zbrange: int = 0, shield_cost: int = 200,
                 shield_hunger: int = 2, gold_hunger: int = 0,
                 sound_set: str = "WARRIOR", domain: int = 0, size: str = "Small"):
        self.ident = ident
        self.name = name
        # Normalize category: CTP2 uses AERIAL not AIR
        self.category = 'UNIT_CATEGORY_AERIAL' if category == 'UNIT_CATEGORY_AIR' else category
        self.attack = attack
        self.defense = defense
        self.sprite = sprite
        self.icon = icon or f"ICON_{ident}"
        self.desc = desc
        self.advance = advance
        self.move = move
        self.hp = hp
        self.firepower = firepower
        self.armor = armor
        self.zbrange = zbrange
        self.shield_cost = shield_cost
        self.shield_hunger = shield_hunger
        self.gold_hunger = gold_hunger
        self.sound_set = sound_set
        self.domain = domain
        self.size = size

    def _block_text(self) -> str:
        """Return a complete, correctly-formatted multi-line unit block."""
        lines = [f"{self.ident} {{"]
        lines += [
            f"   Description DESCRIPTION_{self.ident}",
            f"   DefaultIcon {self.icon}",
            f"   DefaultSprite {self.sprite}",
            f"   Category {self.category}",
            f"   Attack {self.attack}",
            f"   Defense {self.defense}",
            f"   ZBRangeAttack {self.zbrange}",
            f"   Firepower {self.firepower}",
            f"   Armor {self.armor}",
            f"   MaxHP {self.hp}",
            f"   ShieldCost {self.shield_cost}",
            f"   PowerPoints {max(100, self.shield_cost // 2)}",
            f"   ShieldHunger {self.shield_hunger}",
            f"   GoldHunger {self.gold_hunger}",
            f"   FoodHunger 0",
            f"   MaxMovePoints {self.move}",
            f"   VisionRange 2",
        ]
        if self.advance:
            lines.append(f"   EnableAdvance {self.advance}")
        lines += [
            f"   ActiveDefenseRange 0",
            f"   LossMoveToDmgNone",
            f"   MaxFuel 0",
        ]
        if self.domain == 0:
            lines += ["   CanEntrench", "   CanExpel", "   CanPillage",
                      "   CanPirate", "   ExertsMartialLaw", "   DeathEffectsHappy"]
        elif self.domain == 1:
            lines += ["   CantCaptureCity", "   DeathEffectsHappy"]
        else:
            lines += ["   CanPirate", "   CantCaptureCity", "   DeathEffectsHappy"]
        
        # Settlers require these flags at the END of the block to enable "Build City"
        if self.category == 'UNIT_CATEGORY_SETTLER':
            lines += [
                "   NoZoc",
                "   SettleCityType UNIT_CITY",
                "   SettleSize 1",
                "   CanBeExpelled",
                "   CantCaptureCity",
                "   DeathEffectsHappy",
                "   BuildingRemovesAPop",
                "   OnlyBuildOne",
                "   IsSpecialForces",
                "   Civilian",
            ]
        snd = self.sound_set
        lines += [
            f"   SoundSelect1 SOUND_SELECT1_{snd}",
            f"   SoundSelect2 SOUND_SELECT2_{snd}",
            f"   SoundMove SOUND_MOVE_{snd}",
            f"   SoundAcknowledge SOUND_ACKNOWLEDGE_{snd}",
            f"   SoundCantMove SOUND_CANTMOVE_{snd}",
            f"   SoundAttack SOUND_ATTACK_{snd}",
            f"   SoundWork SOUND_WORK_{snd}",
            f"   SoundVictory SOUND_VICTORY_{snd}",
            f"   SoundDeath SOUND_DEATH_{snd}",
            "",
        ]
        if self.domain == 0:
            terrain = [
                "   CanAttack: Land", "   CanAttack: Mountain",
                "   CanSee: Standard",
                "   MovementType: Land", "   MovementType: Mountain",
            ]
            if self.category == 'UNIT_CATEGORY_SETTLER':
                terrain += ["   Settle: Land", "   Settle: Mountain"]
            terrain += [
                f"   Size: {self.size}", "   VisionClass: Standard",
                "   CanReform {",
                "      Sound SOUND_ID_REFORM_CITY",
                "      Effect SPECEFFECT_REFORMCITY",
                "   }",
            ]
            lines += terrain
        elif self.domain == 1:
            lines += [
                "   CanAttack: Land", "   CanAttack: Mountain", "   CanAttack: Air",
                "   CanSee: Standard",
                "   MovementType: Air",
                f"   Size: {self.size}", "   VisionClass: Standard",
            ]
        else:
            lines += [
                "   CanAttack: Sea", "   CanAttack: ShallowWater",
                "   CanSee: Standard",
                "   MovementType: Sea", "   MovementType: ShallowWater",
                f"   Size: {self.size}", "   VisionClass: Standard",
            ]
        lines.append("}")
        return "\n".join(lines)

    def register(self, reg: 'FileRegistry'):
        """Register this unit across all relevant CTP2 files."""
        # Units.txt — append-only; never re-renders existing content
        uni = reg.load("default/gamedata/Units.txt")
        uni.add_unit(self.ident, self._block_text())

        # uniticon.txt — preserve the committed AE/proxy application baseline.
        # Extracted ICON_UNIT_*.TGA assets are applied separately during probe
        # runs so extraction and application stay isolated.
        uic = reg.load("default/gamedata/uniticon.txt")
        if self.icon not in uic.blocks:
            uic.blocks[self.icon] = {
                "FirstFrame": '"UPUP003L.TGA"',
                "Movie": '"NULL"',
                "Gameplay": f'"{self.ident}_GAMEPLAY"',
                "Historical": f'"{self.ident}_HISTORICAL"',
                "Prereq": f'"{self.ident}_PREREQ"',
                "Vari": f'"{self.ident}_STATISTICS"',
                "Icon": '"UPUP003A.TGA"',
                "LargeIcon": '"UPUP003L.TGA"',
                "SmallIcon": '"UPUP003B.TGA"',
                "StatText": f'"{self.ident}_SUMMARY"',
            }

        # gl_str.txt
        s = reg.load("english/gamedata/gl_str.txt")
        s.entries[self.ident] = self.name
        s.entries[f"DESCRIPTION_{self.ident}"] = self.desc or f"A Master of Magic unit: {self.name}."

        # Great_Library.txt
        gl = reg.load("english/gamedata/Great_Library.txt")
        if self.advance:
            adv_label = self.advance.split('_', 1)[1].replace('_', ' ').title() \
                if '_' in self.advance else self.advance
            prereq_text = (f"Requires:\n"
                           f"<L:DATABASE_ADVANCES,{self.advance}>{adv_label}<e>")
        else:
            prereq_text = "Requires:\nNothing"
        stats_text = "\n".join([
            "Attack: {UnitDB(UnitRecord[0]).Attack / 100}",
            "Ranged: {UnitDB(UnitRecord[0]).ZBRangeAttack}",
            "Defense: {UnitDB(UnitRecord[0]).Defense / 100}",
            "Armor: {UnitDB(UnitRecord[0]).Armor / 100}",
            "Damage: {UnitDB(UnitRecord[0]).Firepower}",
            "Vision: {UnitDB(UnitRecord[0]).VisionRange}",
            "Movement: {UnitDB(UnitRecord[0]).MaxMovePoints / 10000}",
            "Max HP: {UnitDB(UnitRecord[0]).MaxHP}",
            "Costs: {UnitDB(UnitRecord[0]).ShieldCost}",
            "Upkeep: {UnitDB(UnitRecord[0]).ShieldHunger} Shields",
            "Food Hunger: {UnitDB(UnitRecord[0]).FoodHunger}",
        ])
        gl.sections.setdefault(f"{self.ident}_PREREQ", prereq_text)
        gl.sections.setdefault(f"{self.ident}_STATISTICS", stats_text)
        gl.sections.setdefault(f"{self.ident}_SUMMARY",
                               f"{self.name}: a Master of Magic proxy unit.")
        gl.sections.setdefault(f"{self.ident}_GAMEPLAY",
                               f"The {self.name} is a unit from Master of Magic.")
        gl.sections.setdefault(f"{self.ident}_HISTORICAL",
                               f"The {self.name} is represented here as a proxy unit "
                               f"while the final MoM art swap is in progress.")

    def check(self, reg: 'FileRegistry') -> List[str]:
        errors = []
        uni = reg.load("default/gamedata/Units.txt")
        if not uni.has_unit(self.ident):
            errors.append(f"{self.ident} not in Units.txt")
        uic = reg.load("default/gamedata/uniticon.txt")
        if self.icon not in uic.blocks:
            errors.append(f"{self.icon} not in uniticon.txt")
        return errors
