# Intermediate Code Generator

![Python](https://img.shields.io/badge/python-3.8%2B-blue) ![License](https://img.shields.io/badge/license-MIT-green)

A compiler front end that translates a small C-like language into **three-address code (TAC)**, **quadruples** and **triples**. It was built as a **Compiler Construction mini project** and comes in two forms:

- a **command-line compiler** written in Python (`icg.py`), and
- **ICG Studio**, a browser-based interface that runs the same compiler logic in JavaScript (`docs/index.html`).

> This is a teaching project, not a production compiler.

**Live demo:** `https://<your-username>.github.io/intermediate-code-generator/` (enable GitHub Pages for the `/docs` folder)

## Screenshots

| Output | Three-address code |
|---|---|
| ![Output](docs/screenshots/01-output.png) | ![TAC](docs/screenshots/02-tac.png) |
| **Quadruples** | **Triples** |
| ![Quadruples](docs/screenshots/03-quadruples.png) | ![Triples](docs/screenshots/04-triples.png) |

**Error detection:** the faulty line is highlighted and the failing phase is marked in the pipeline.

![Error detection](docs/screenshots/05-error-detection.png)

## Features

- Lexical analysis, recursive-descent parsing and semantic analysis with a symbol table
- Three-address code with temporaries (`t1`, `t2`, ...) and labels (`L1`, `L2`, ...)
- Quadruple and triple representations
- Short-circuit evaluation of `&&` and `||`
- Optional **constant folding**
- A built-in **TAC interpreter** that runs the generated code to verify it
- Errors reported with line numbers
- Browser interface with a phase pipeline, line-numbered editor and tabs for output, TAC, quadruples, triples, symbols and tokens

## Pipeline

```
Source code -> Lexer -> Parser (syntax tree) -> Semantic analysis (symbol table)
            -> Three-address code -> Quadruples / Triples -> TAC interpreter
```

## Quick start

Requires Python 3.8 or newer. No external libraries are needed.

```bash
git clone https://github.com/<your-username>/intermediate-code-generator.git
cd intermediate-code-generator

python icg.py samples/factorial.src --run
python icg.py samples/expr.src --fold --run --tokens --ast
python icg.py samples/gcd.src -o gcd.tac
```

| Option | Meaning |
|---|---|
| `--run` | Execute the generated TAC and print the program output |
| `--fold` | Enable constant folding |
| `--tokens` | Show the token stream |
| `--ast` | Show the syntax tree |
| `-o FILE` | Save the TAC to a file |

### Web version

Open `docs/index.html` in any browser, pick a sample or type a program, and press **Compile & Run** (or Ctrl + Enter).

## The language

```c
// factorial of n using a for loop
int n = 5, f = 1, i;
for (i = 1; i <= n; i = i + 1) {
    f = f * i;
}
print(f);
```

| Feature | Syntax |
|---|---|
| Declarations | `int a, b = 5;` `float x;` |
| Assignment | `a = b + 2 * 3;` |
| Arithmetic | `+ - * / %` and unary `-` |
| Relational | `< > <= >= == !=` |
| Logical | `&& \|\| !` |
| Control flow | `if / else`, `while`, `for` |
| Output | `print(expr);` |
| Comments | `// text` |

## Example output

For the program above, the compiler generates:

```
n = 5
f = 1
i = 1
L1:
t1 = i <= n
ifFalse t1 goto L2
t2 = f * i
f = t2
t3 = i + 1
i = t3
goto L1
L2:
print f
```

and the interpreter prints `120`.

### Constant folding

For `k = 2 * 3 + 4;`:

| Folding off | Folding on |
|---|---|
| `t1 = 2 * 3` | |
| `t2 = t1 + 4` | `k = 10` |
| `k = t2` | |

### How control flow is translated

| Statement | Generated code |
|---|---|
| `if (C) S1 else S2` | `ifFalse C goto Lelse`, S1, `goto Lend`, `Lelse:`, S2, `Lend:` |
| `while (C) S` | `Lstart:`, `ifFalse C goto Lend`, S, `goto Lstart`, `Lend:` |
| `for (I; C; U) S` | I, `Lstart:`, `ifFalse C goto Lend`, S, U, `goto Lstart`, `Lend:` |

## Project structure

```
intermediate-code-generator/
|-- icg.py             # lexer, parser, code generator, interpreter (CLI)
|-- test_icg.py        # unit tests
|-- samples/           # example programs (factorial, gcd, expressions)
|-- docs/
|   |-- index.html     # ICG Studio (web version, GitHub Pages)
|   |-- report.pdf     # project report
|   `-- screenshots/
|-- LICENSE
`-- README.md
```

## Testing

Run the tests from the repository root (they read the files in `samples/`):

```bash
python -m unittest test_icg -v
```

The 11 tests cover operator precedence, unary minus, if/else, while and for loops, GCD, short-circuit evaluation, constant folding, and error reporting (undeclared variable, redeclaration, syntax error).

## Limitations

- Single global scope; `int` and `float` are tracked but there is no full type checking.
- Constant folding is the only optimisation, and no target (assembly) code is generated.
- Triples for `&&` and `||` are approximate because the short-circuit code reuses one temporary. The TAC and quadruples are exact.
- The web version uses JavaScript numbers, so a float result such as `4.0 / 2.0` is shown as `2`, and it is not covered by the automated tests.
- Variable names of the form `t<number>` and `L<number>` are reserved for compiler temporaries and labels.

## Future work

- More optimisations (copy propagation, common subexpression and dead-code elimination)
- Functions, arrays and nested scopes, with type checking
- Target (assembly) code generation
- Step-by-step TAC execution and a control-flow graph view

## Author

**Jeena Joseph**, B.Tech Computer Science and Engineering, St. Vincent Pallotti College of Engineering and Technology, Nagpur.
