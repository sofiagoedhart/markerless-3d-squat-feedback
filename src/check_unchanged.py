"""Compare two versions of a file for behaviour, ignoring comments and docstrings."""
import ast
import sys


def stripped(path):
    tree = ast.parse(open(path, encoding="utf-8").read())
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef,
                                 ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        body = node.body
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    return ast.dump(ast.fix_missing_locations(tree))


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    a, b = sys.argv[1], sys.argv[2]
    same = stripped(a) == stripped(b)
    print(f"{'IDENTICAL' if same else 'DIFFERENT'}  {a} vs {b}")
    sys.exit(0 if same else 1)


if __name__ == "__main__":
    main()
