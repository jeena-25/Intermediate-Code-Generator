#!/usr/bin/env python3
"""
Intermediate Code Generator
===========================
Pipeline:
    source -> Lexer -> Parser (AST) -> Semantic checks (symbol table)
           -> Three-Address Code (TAC) -> Quadruples / Triples
           -> (optional) TAC interpreter to verify the generated code

Source language (mini C):
    declarations : int a, b = 5;   float x;
    assignment   : a = b + 2 * 3;
    control flow : if (...) {...} else {...}   while (...) {...}   for (i = 0; i < n; i = i + 1) {...}
    output       : print(expr);
    operators    : + - * / %   < > <= >= == !=   && || !   unary -
    comments     : // to end of line

Usage:
    python icg.py samples/factorial.src
    python icg.py samples/expr.src --fold --run --tokens --ast
"""
import argparse
import math
import re
import sys
from collections import namedtuple
from pprint import pformat


class CompileError(Exception):
    pass


Quad = namedtuple("Quad", "op a1 a2 res")

# ---------------------------------------------------------------- 1. LEXER
KEYWORDS = {"int", "float", "if", "else", "while", "for", "print"}
TOKEN_SPEC = [
    ("COMMENT", r"//[^\n]*"),
    ("NUM", r"\d+(?:\.\d+)?"),
    ("ID", r"[A-Za-z_]\w*"),
    ("OP", r"==|!=|<=|>=|&&|\|\||[+\-*/%<>=!]"),
    ("PUNCT", r"[(){};,]"),
    ("SKIP", r"[ \t\r]+"),
    ("NEWLINE", r"\n"),
    ("MISMATCH", r"."),
]
MASTER = re.compile("|".join(f"(?P<{n}>{p})" for n, p in TOKEN_SPEC))


def tokenize(src):
    """Return a list of (kind, text, line) tokens ending with an EOF token."""
    toks, line = [], 1
    for m in MASTER.finditer(src):
        kind, text = m.lastgroup, m.group()
        if kind == "NEWLINE":
            line += 1
        elif kind in ("SKIP", "COMMENT"):
            continue
        elif kind == "MISMATCH":
            raise CompileError(f"line {line}: illegal character {text!r}")
        else:
            if kind == "ID" and text in KEYWORDS:
                kind = "KW"
            toks.append((kind, text, line))
    toks.append(("EOF", "", line))
    return toks


# --------------------------------------------------------------- 2. PARSER
# Recursive-descent parser. Grammar (lowest to highest precedence):
#   expr     -> and  ( '||' and )*
#   and      -> eq   ( '&&' eq )*
#   eq       -> rel  ( ('=='|'!=') rel )*
#   rel      -> add  ( ('<'|'>'|'<='|'>=') add )*
#   add      -> mul  ( ('+'|'-') mul )*
#   mul      -> unary( ('*'|'/'|'%') unary )*
#   unary    -> ('-'|'!') unary | primary
#   primary  -> NUM | ID | '(' expr ')'
class Parser:
    def __init__(self, toks):
        self.t, self.i = toks, 0

    def peek(self):
        return self.t[self.i]

    def next(self):
        tok = self.t[self.i]
        self.i += 1
        return tok

    def at(self, val):
        kind, v, _ = self.peek()
        return v == val and kind in ("KW", "OP", "PUNCT")

    def accept(self, val):
        if self.at(val):
            return self.next()
        return None

    def expect(self, val):
        if not self.at(val):
            _, v, line = self.peek()
            raise CompileError(f"line {line}: expected '{val}' but found {v or 'end of input'!r}")
        return self.next()

    # ---- statements
    def program(self):
        stmts = []
        while self.peek()[0] != "EOF":
            stmts.append(self.statement())
        return stmts

    def statement(self):
        kind, val, line = self.peek()
        if self.at("{"):
            return self.block()
        if kind == "KW" and val in ("int", "float"):
            return self.decl()
        if self.at("if"):
            return self.if_stmt()
        if self.at("while"):
            self.next(); self.expect("(")
            cond = self.expr(); self.expect(")")
            return ("while", cond, self.statement())
        if self.at("for"):
            return self.for_stmt()
        if self.at("print"):
            self.next(); self.expect("(")
            e = self.expr(); self.expect(")"); self.expect(";")
            return ("print", e)
        if kind == "ID":
            a = self.assign_expr(); self.expect(";")
            return a
        raise CompileError(f"line {line}: unexpected token {val or 'end of input'!r}")

    def block(self):
        self.expect("{")
        stmts = []
        while not self.at("}"):
            if self.peek()[0] == "EOF":
                raise CompileError(f"line {self.peek()[2]}: missing '}}'")
            stmts.append(self.statement())
        self.expect("}")
        return ("block", stmts)

    def decl(self):
        typ = self.next()[1]
        items = []
        while True:
            tok = self.next()
            if tok[0] != "ID":
                raise CompileError(f"line {tok[2]}: expected a variable name in declaration")
            init = self.expr() if self.accept("=") else None
            items.append((tok[1], init, tok[2]))
            if not self.accept(","):
                break
        self.expect(";")
        return ("decl", typ, items)

    def assign_expr(self):
        tok = self.next()
        if tok[0] != "ID":
            raise CompileError(f"line {tok[2]}: expected a variable name")
        self.expect("=")
        return ("assign", tok[1], self.expr(), tok[2])

    def if_stmt(self):
        self.expect("if"); self.expect("(")
        cond = self.expr(); self.expect(")")
        then = self.statement()
        els = self.statement() if self.accept("else") else None
        return ("if", cond, then, els)

    def for_stmt(self):
        self.expect("for"); self.expect("(")
        init = self.assign_expr(); self.expect(";")
        cond = self.expr(); self.expect(";")
        step = self.assign_expr(); self.expect(")")
        return ("for", init, cond, step, self.statement())

    # ---- expressions
    def binary(self, sub, ops):
        left = sub()
        while self.peek()[0] == "OP" and self.peek()[1] in ops:
            op = self.next()[1]
            left = ("bin", op, left, sub())
        return left

    def expr(self):  return self.binary(self.and_, {"||"})
    def and_(self):  return self.binary(self.eq, {"&&"})
    def eq(self):    return self.binary(self.rel, {"==", "!="})
    def rel(self):   return self.binary(self.add, {"<", ">", "<=", ">="})
    def add(self):   return self.binary(self.mul, {"+", "-"})
    def mul(self):   return self.binary(self.unary, {"*", "/", "%"})

    def unary(self):
        if self.peek()[0] == "OP" and self.peek()[1] in ("-", "!"):
            op = self.next()[1]
            return ("un", op, self.unary())
        return self.primary()

    def primary(self):
        kind, val, line = self.peek()
        if kind == "NUM":
            self.next()
            return ("num", float(val) if "." in val else int(val))
        if kind == "ID":
            self.next()
            return ("var", val, line)
        if self.accept("("):
            e = self.expr()
            self.expect(")")
            return e
        raise CompileError(f"line {line}: unexpected token {val or 'end of input'!r}")


# ----------------------------------------------------- 3. SHARED ARITHMETIC
def parse_num(s):
    return float(s) if "." in s else int(s)


def is_num(s):
    try:
        parse_num(s)
        return True
    except ValueError:
        return False


def apply_op(op, a, b):
    """Evaluate a binary operator (used by constant folding and the interpreter)."""
    if op in ("/", "%") and b == 0:
        raise CompileError("division by zero")
    both_int = isinstance(a, int) and isinstance(b, int)
    return {
        "+": lambda: a + b,
        "-": lambda: a - b,
        "*": lambda: a * b,
        "/": lambda: int(a / b) if both_int else a / b,
        "%": lambda: int(math.fmod(a, b)) if both_int else math.fmod(a, b),
        "<": lambda: int(a < b), ">": lambda: int(a > b),
        "<=": lambda: int(a <= b), ">=": lambda: int(a >= b),
        "==": lambda: int(a == b), "!=": lambda: int(a != b),
    }[op]()


# -------------------------------------------- 4. SEMANTICS + TAC GENERATION
TEMP_OR_LABEL = re.compile(r"^[tL]\d+$")


class CodeGen:
    def __init__(self, fold=False):
        self.quads, self.symbols = [], {}
        self.fold, self._t, self._l = fold, 0, 0

    def temp(self):
        self._t += 1
        return f"t{self._t}"

    def label(self):
        self._l += 1
        return f"L{self._l}"

    def emit(self, op, a1="", a2="", res=""):
        self.quads.append(Quad(op, a1, a2, res))

    # ---- symbol table
    def declare(self, name, typ, line):
        if TEMP_OR_LABEL.match(name):
            raise CompileError(f"line {line}: '{name}' is reserved for compiler temporaries/labels")
        if name in self.symbols:
            raise CompileError(f"line {line}: '{name}' already declared")
        self.symbols[name] = typ

    def check(self, name, line):
        if name not in self.symbols:
            raise CompileError(f"line {line}: '{name}' used before declaration")

    # ---- driver
    def generate(self, ast):
        for s in ast:
            self.stmt(s)
        return self.quads

    def stmt(self, n):
        k = n[0]
        if k == "block":
            for s in n[1]:
                self.stmt(s)
        elif k == "decl":
            for name, init, line in n[2]:
                self.declare(name, n[1], line)
                if init is not None:
                    self.emit("=", self.expr(init), "", name)
        elif k == "assign":
            self.check(n[1], n[3])
            self.emit("=", self.expr(n[2]), "", n[1])
        elif k == "print":
            self.emit("print", self.expr(n[1]))
        elif k == "if":
            c = self.expr(n[1])
            l_else, l_end = self.label(), (self.label() if n[3] else None)
            self.emit("ifFalse", c, "", l_else)
            self.stmt(n[2])
            if n[3]:
                self.emit("goto", "", "", l_end)
            self.emit("label", "", "", l_else)
            if n[3]:
                self.stmt(n[3])
                self.emit("label", "", "", l_end)
        elif k == "while":
            l_start, l_end = self.label(), self.label()
            self.emit("label", "", "", l_start)
            self.emit("ifFalse", self.expr(n[1]), "", l_end)
            self.stmt(n[2])
            self.emit("goto", "", "", l_start)
            self.emit("label", "", "", l_end)
        elif k == "for":
            self.stmt(n[1])
            l_start, l_end = self.label(), self.label()
            self.emit("label", "", "", l_start)
            self.emit("ifFalse", self.expr(n[2]), "", l_end)
            self.stmt(n[4])
            self.stmt(n[3])
            self.emit("goto", "", "", l_start)
            self.emit("label", "", "", l_end)

    def expr(self, n):
        """Generate code for an expression; return the operand holding its value."""
        k = n[0]
        if k == "num":
            return str(n[1])
        if k == "var":
            self.check(n[1], n[2])
            return n[1]
        if k == "un":
            v = self.expr(n[2])
            if self.fold and is_num(v):
                x = parse_num(v)
                return str(-x if n[1] == "-" else int(not x))
            t = self.temp()
            self.emit("uminus" if n[1] == "-" else "!", v, "", t)
            return t
        op = n[1]
        if op in ("&&", "||"):
            return self.logical(n)
        l, r = self.expr(n[2]), self.expr(n[3])
        if self.fold and is_num(l) and is_num(r):
            return str(apply_op(op, parse_num(l), parse_num(r)))
        t = self.temp()
        self.emit(op, l, r, t)
        return t

    def logical(self, n):
        """Short-circuit evaluation of && and || using conditional jumps."""
        op, end = n[1], self.label()
        l = self.expr(n[2])
        t = self.temp()
        self.emit("!=", l, "0", t)
        self.emit("ifFalse" if op == "&&" else "ifTrue", t, "", end)
        r = self.expr(n[3])
        self.emit("!=", r, "0", t)
        self.emit("label", "", "", end)
        return t


# ------------------------------------------------------ 5. OUTPUT FORMATS
def fmt_tac(q):
    op, a, b, r = q
    if op == "label":
        return f"{r}:"
    if op == "goto":
        return f"    goto {r}"
    if op in ("ifFalse", "ifTrue"):
        return f"    {op} {a} goto {r}"
    if op == "=":
        return f"    {r} = {a}"
    if op == "uminus":
        return f"    {r} = -{a}"
    if op == "!":
        return f"    {r} = !{a}"
    if op == "print":
        return f"    print {a}"
    return f"    {r} = {a} {op} {b}"


def resolve(quads):
    """Drop label pseudo-instructions; map each label to the index of the next instruction."""
    instrs, label_at = [], {}
    for q in quads:
        if q.op == "label":
            label_at[q.res] = len(instrs)
        else:
            instrs.append(q)
    return instrs, label_at


def quad_rows(quads):
    instrs, label_at = resolve(quads)
    rows = []
    for i, q in enumerate(instrs):
        res = str(label_at[q.res]) if q.op in ("goto", "ifFalse", "ifTrue") else q.res
        rows.append((i, q.op, q.a1 or "-", q.a2 or "-", res or "-"))
    return ["#", "op", "arg1", "arg2", "result"], rows


def triple_rows(quads):
    instrs, label_at = resolve(quads)
    temp_at, rows = {}, []

    def ref(x):
        return f"({temp_at[x]})" if x in temp_at else (x or "-")

    for i, q in enumerate(instrs):
        if q.op == "=":
            rows.append((i, "=", q.res, ref(q.a1)))
        elif q.op == "goto":
            rows.append((i, "goto", f"({label_at[q.res]})", "-"))
        elif q.op in ("ifFalse", "ifTrue"):
            rows.append((i, q.op, ref(q.a1), f"({label_at[q.res]})"))
        elif q.op == "print":
            rows.append((i, "print", ref(q.a1), "-"))
        else:
            rows.append((i, q.op, ref(q.a1), ref(q.a2)))
            temp_at[q.res] = i
    return ["#", "op", "arg1", "arg2"], rows


def table(headers, rows):
    rows = [[str(c) for c in r] for r in rows]
    w = [max(len(h), *(len(r[i]) for r in rows)) if rows else len(h) for i, h in enumerate(headers)]
    line = "+" + "+".join("-" * (x + 2) for x in w) + "+"
    fmt = lambda r: "| " + " | ".join(c.ljust(w[i]) for i, c in enumerate(r)) + " |"
    return "\n".join([line, fmt(headers), line, *(fmt(r) for r in rows), line])


# ---------------------------------------------- 6. TAC INTERPRETER (verify)
def run(quads, symbols, max_steps=1_000_000):
    """Execute the generated TAC and return everything that was printed."""
    instrs, label_at = resolve(quads)
    env = {name: 0 for name in symbols}
    out, pc, steps = [], 0, 0

    def val(x):
        return env[x] if x in env else parse_num(x)

    while pc < len(instrs):
        steps += 1
        if steps > max_steps:
            raise CompileError("execution aborted: too many steps (infinite loop?)")
        op, a, b, r = instrs[pc]
        pc += 1
        if op == "=":
            v = val(a)
            env[r] = int(v) if symbols.get(r) == "int" else v
        elif op == "goto":
            pc = label_at[r]
        elif op == "ifFalse" and not val(a):
            pc = label_at[r]
        elif op == "ifTrue" and val(a):
            pc = label_at[r]
        elif op == "print":
            out.append(str(val(a)))
        elif op == "uminus":
            env[r] = -val(a)
        elif op == "!":
            env[r] = int(not val(a))
        elif op not in ("ifFalse", "ifTrue"):
            env[r] = apply_op(op, val(a), val(b))
    return out


# ------------------------------------------------------------------ MAIN
def compile_source(src, fold=False):
    tokens = tokenize(src)
    ast = Parser(tokens).program()
    gen = CodeGen(fold)
    quads = gen.generate(ast)
    return tokens, ast, gen.symbols, quads


def main():
    ap = argparse.ArgumentParser(description="Intermediate Code Generator (three-address code)")
    ap.add_argument("source", nargs="?", help="source file (reads stdin if omitted)")
    ap.add_argument("--fold", action="store_true", help="enable constant folding")
    ap.add_argument("--run", action="store_true", help="execute the generated TAC")
    ap.add_argument("--tokens", action="store_true", help="show the token stream")
    ap.add_argument("--ast", action="store_true", help="show the syntax tree")
    ap.add_argument("-o", "--output", help="write the TAC to a file")
    args = ap.parse_args()

    src = open(args.source).read() if args.source else sys.stdin.read()
    try:
        tokens, ast, symbols, quads = compile_source(src, args.fold)
        print("=== SOURCE ===")
        print(src.rstrip())
        if args.tokens:
            print("\n=== TOKENS ===")
            print(table(["kind", "lexeme", "line"], tokens[:-1]))
        if args.ast:
            print("\n=== SYNTAX TREE ===")
            print(pformat(ast, width=90))
        print("\n=== SYMBOL TABLE ===")
        print(table(["name", "type"], sorted(symbols.items())))
        tac = "\n".join(fmt_tac(q) for q in quads)
        print("\n=== THREE-ADDRESS CODE ===")
        print(tac)
        print("\n=== QUADRUPLES ===")
        print(table(*quad_rows(quads)))
        print("\n=== TRIPLES ===")
        print(table(*triple_rows(quads)))
        if args.run:
            print("\n=== PROGRAM OUTPUT (TAC interpreter) ===")
            print("\n".join(run(quads, symbols)) or "(no output)")
        if args.output:
            with open(args.output, "w") as f:
                f.write(tac + "\n")
    except CompileError as e:
        print(f"Compile error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
