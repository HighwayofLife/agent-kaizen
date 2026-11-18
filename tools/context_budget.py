#!/usr/bin/env python3
"""Check the repository's reviewed model-visible context budget."""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


def frontmatter(path):
    lines = path.read_text(encoding='utf-8').splitlines()
    if not lines or lines[0] != '---' or '---' not in lines[1:]:
        raise ValueError('{}: malformed frontmatter delimiters'.format(path))
    fields = {}
    front = lines[1:lines.index('---', 1)]
    for index, line in enumerate(front):
        if not line.strip() or line.lstrip().startswith('#') or line[0].isspace():
            continue
        match = re.fullmatch(r'([\w-]+):\s*(.*)', line)
        if not match or match.group(1) in fields:
            raise ValueError('{}: malformed frontmatter line: {}'.format(path, line))
        key, value = match.groups()
        if value in ('>', '>-', '|', '|-'):
            block = []
            for following in front[index + 1:]:
                if following and not following[0].isspace():
                    break
                block.append(following.strip())
            value = (' ' if value.startswith('>') else '\n').join(block)
            if not match.group(2).endswith('-'):
                value += '\n'
        if value.startswith(('[', '{')):
            stack = []
            quote = None
            escaped = False
            for char in value:
                if quote:
                    if escaped:
                        escaped = False
                    elif char == '\\' and quote == '"':
                        escaped = True
                    elif char == quote:
                        quote = None
                elif char in ('"', "'"):
                    quote = char
                elif char in '[{':
                    stack.append(char)
                elif char in ']}':
                    if not stack or stack.pop() != {']': '[', '}': '{'}[char]:
                        raise ValueError('{}: malformed flow value for {}'.format(path, key))
            if stack or quote:
                raise ValueError('{}: malformed flow value for {}'.format(path, key))
        if value.startswith(('"', "'")):
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError('{}: malformed quoted value for {}'.format(path, key))
            if value[0] == '"':
                try:
                    value = json.loads(value)
                except ValueError as exc:
                    raise ValueError('{}: malformed quoted value: {}'.format(path, exc))
            else:
                value = value[1:-1].replace("''", "'")
        fields[key] = value
    if not fields.get('description'):
        raise ValueError('{}: missing description'.format(path))
    return fields


def check(root):
    config = json.loads((root / 'tools/context-budget.json').read_text(encoding='utf-8'))
    manifest = json.loads((root / 'hooks/hooks.json').read_text(encoding='utf-8'))
    inventory = config['hooks']
    total = 0
    errors = []
    for kind, pattern in (('agent', 'agents/*.md'), ('skill', 'skills/*/SKILL.md')):
        for path in sorted(root.glob(pattern)):
            fields = frontmatter(path)
            disabled = fields.get('disable-model-invocation')
            visible = kind == 'agent' or disabled != 'true'
            size = len(fields['description'].encode('utf-8')) if visible else 0
            total += size
            print('{} {}: {} bytes{}'.format(kind, path.relative_to(root), size,
                                              '' if visible else ' (disabled)'))
            if kind == 'skill' and disabled != 'true':
                errors.append('{}: missing disable-model-invocation: true'.format(path))
    registered = set()
    for groups in manifest['hooks'].values():
        for group in groups:
            for hook in group['hooks']:
                command = hook.get('command', '')
                matches = re.findall(r'\$\{CLAUDE_PLUGIN_ROOT\}/(hooks/[\w.-]+\.sh)', command)
                if hook.get('type') != 'command' or not matches:
                    raise ValueError('unsupported registered hook: {}'.format(hook))
                registered.update(matches)
    for name in sorted(registered):
        if name not in inventory:
            errors.append('{}: missing registered-hook inventory entry'.format(name))
            continue
        entry = inventory[name]
        size = entry['literal_bytes']
        if type(size) is not int or size < 0:
            raise ValueError('{}: invalid literal_bytes'.format(name))
        if len(entry['literal_text'].encode('utf-8')) != size:
            raise ValueError('{}: literal_text does not match literal_bytes'.format(name))
        digest = hashlib.sha256((root / name).read_bytes()).hexdigest()
        if digest != entry['sha256']:
            errors.append('{}: hook changed; review and update inventory'.format(name))
        total += size
        print('hook {}: {} reviewed literal bytes'.format(name, size))
    print('Total: {} UTF-8 bytes; bytes/4 proxy: {:.2f}; budget: {} bytes'.format(
        total, total / 4, config['budget_bytes']))
    if total > config['budget_bytes']:
        errors.append('over budget by {} bytes'.format(total - config['budget_bytes']))
    for error in errors:
        print('ERROR: {}'.format(error), file=sys.stderr)
    return bool(errors)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()
    try:
        return check(args.root)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print('ERROR: {}'.format(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
