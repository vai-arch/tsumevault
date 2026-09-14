"""
sgf_lib.py — Minimal, dependency-free SGF (Smart Game Format) parser and
TsumeVault-specific problem validator for the my_collection import pipeline.

Only implements what's needed to read Drago-style life-and-death problem
files: node/property/value parsing with SGF text escaping, and a game-tree
structure that mirrors what tsumevault.html actually walks at runtime
(setupInteractiveMode / checkResult / playOpponent), so validation results
match the app's real behavior rather than a generic SGF sanity check.
"""


class SGFParseError(Exception):
    pass


class Node:
    __slots__ = ('props', 'children')

    def __init__(self, props=None):
        self.props = props or {}
        self.children = []

    def first(self, key):
        vals = self.props.get(key)
        return vals[0] if vals else None

    @property
    def comment(self):
        return self.first('C') or ''

    @property
    def move_color(self):
        """Returns 'B' or 'W' if this node places a stone, else None."""
        if 'B' in self.props:
            return 'B'
        if 'W' in self.props:
            return 'W'
        return None


def _skip_ws(s, i):
    while i < len(s) and s[i] in ' \t\r\n':
        i += 1
    return i


def _parse_prop_value(s, i):
    # s[i] == '['
    i += 1
    out = []
    while i < len(s):
        c = s[i]
        if c == '\\':
            nxt = s[i + 1] if i + 1 < len(s) else ''
            if nxt in ('\r', '\n'):
                # soft line break: the backslash+newline is removed entirely
                i += 2
                if nxt == '\r' and i < len(s) and s[i] == '\n':
                    i += 1
                continue
            if nxt:
                out.append(nxt)
                i += 2
                continue
            i += 1
            continue
        if c == ']':
            return ''.join(out), i + 1
        out.append(c)
        i += 1
    raise SGFParseError('unterminated property value')


def _parse_node(s, i):
    # s[i] == ';'
    i += 1
    props = {}
    while True:
        i = _skip_ws(s, i)
        if i < len(s) and s[i].isalpha() and s[i].isupper():
            j = i
            while j < len(s) and s[j].isalpha() and s[j].isupper():
                j += 1
            ident = s[i:j]
            i = _skip_ws(s, j)
            values = []
            while i < len(s) and s[i] == '[':
                val, i = _parse_prop_value(s, i)
                values.append(val)
                i = _skip_ws(s, i)
            props[ident] = values
        else:
            break
    return props, i


def _parse_game_tree(s, i):
    # s[i] == '('
    i += 1
    seq = []
    while True:
        i = _skip_ws(s, i)
        if i < len(s) and s[i] == ';':
            props, i = _parse_node(s, i)
            seq.append(props)
        else:
            break
    i = _skip_ws(s, i)
    subtrees = []
    while i < len(s) and s[i] == '(':
        head, i = _parse_game_tree(s, i)
        subtrees.append(head)
        i = _skip_ws(s, i)
    if i >= len(s) or s[i] != ')':
        raise SGFParseError(f'expected ")" at position {i}')
    i += 1
    if not seq:
        if len(subtrees) == 1:
            return subtrees[0], i
        raise SGFParseError('game tree has no nodes')
    nodes = [Node(p) for p in seq]
    for a, b in zip(nodes, nodes[1:]):
        a.children.append(b)
    nodes[-1].children.extend(subtrees)
    return nodes[0], i


def parse_sgf(text):
    """Parses one SGF file's text and returns the root Node."""
    i = _skip_ws(text, 0)
    if i >= len(text) or text[i] != '(':
        raise SGFParseError('does not start with "("')
    root, i = _parse_game_tree(text, i)
    # Drago files only ever contain a single top-level game tree; trailing
    # content (there shouldn't be any) is not treated as fatal.
    return root


def _walk(node, depth=0):
    yield node, depth
    for c in node.children:
        yield from _walk(c, depth + 1)


def _comment_status(node):
    c = (node.comment or '').strip().upper()
    if c.startswith('RIGHT'):
        return 'RIGHT'
    if c.startswith('WRONG'):
        return 'WRONG'
    return None


def validate_problem(root):
    """Walks the full tree exactly the way tsumevault.html's
    setupInteractiveMode/checkResult/playOpponent do, and returns:
        {
          'color_to_play': 'B' | 'W' | None,
          'issues': [(severity, message), ...],
          'has_error': bool,
          'has_broken': bool,
        }

    Severities:
      ERROR   - structural problem; the problem is always excluded.
      BROKEN  - the app will mis-score or stall on this branch at runtime
                (an opponent-reply/epilogue leaf with no matching comment);
                excludes the problem unless the caller overrides it.
      WARNING - informational / worth a look, never excludes the problem.
      COSMETIC- a player-move leaf with no matching comment; the app's own
                fallback already treats this as correct, so it's safe, but
                still surfaced in case it's an unintentional typo.
    """
    issues = []
    color_to_play = None

    if not root.props.get('SZ'):
        issues.append(('WARNING', 'missing SZ (board size) tag'))

    branches = root.children
    if not branches:
        issues.append(('ERROR', 'no branches found under the setup node'))
        return {'color_to_play': None, 'issues': issues,
                'has_error': True, 'has_broken': False}

    first_colors = set()
    for b in branches:
        c = b.move_color
        if not c:
            issues.append(('ERROR',
                            f'a first-level branch has no B/W move (props: {sorted(b.props)})'))
        else:
            first_colors.add(c)
    if len(first_colors) > 1:
        issues.append(('ERROR',
                        f'inconsistent first-move color across branches: {sorted(first_colors)}'))
    elif len(first_colors) == 1:
        color_to_play = next(iter(first_colors))

    for node, depth in _walk(root, 0):
        if depth == 0:
            continue
        status = _comment_status(node)
        role = 'player' if depth % 2 == 1 else 'opponent'
        if node.children:
            if status is not None:
                issues.append(('WARNING',
                                f'depth {depth}: has a {status} comment but still has '
                                f'children -- those children are unreachable'))
            if role == 'opponent' and len(node.children) > 1:
                issues.append(('WARNING',
                                f'depth {depth}: opponent-slot node has {len(node.children)} '
                                f'children -- only the first is ever auto-played'))
        else:
            if status is None:
                if role == 'player':
                    issues.append(('COSMETIC',
                                    f'depth {depth}: player-move leaf has no RIGHT/WRONG comment '
                                    f'(app defaults an uncommented player leaf to correct)'))
                else:
                    issues.append(('BROKEN',
                                    f'depth {depth}: opponent-reply/epilogue leaf has no RIGHT/WRONG '
                                    f"comment -- the app will stall here and misregister the player's "
                                    f'next click as WRONG'))

    has_error = any(sev == 'ERROR' for sev, _ in issues)
    has_broken = any(sev == 'BROKEN' for sev, _ in issues)
    return {'color_to_play': color_to_play, 'issues': issues,
            'has_error': has_error, 'has_broken': has_broken}
