import unittest
from icg import compile_source, run, CompileError


def output(src, fold=False):
    _, _, symbols, quads = compile_source(src, fold)
    return run(quads, symbols)


class ICGTests(unittest.TestCase):
    def test_precedence(self):
        self.assertEqual(output("int a; a = 2 + 3 * 4; print(a);"), ["14"])

    def test_parentheses_and_unary(self):
        self.assertEqual(output("int a; a = -(2 + 3) * 2; print(a);"), ["-10"])

    def test_if_else(self):
        self.assertEqual(output("int a = 3; if (a > 5) { print(1); } else { print(2); }"), ["2"])

    def test_while(self):
        self.assertEqual(output("int i = 0; while (i < 3) { print(i); i = i + 1; }"), ["0", "1", "2"])

    def test_for_factorial(self):
        src = open("samples/factorial.src").read()
        self.assertEqual(output(src), ["120"])

    def test_gcd(self):
        self.assertEqual(output(open("samples/gcd.src").read()), ["6"])

    def test_short_circuit(self):
        # right operand would divide by zero; && must not evaluate it
        self.assertEqual(output("int a = 0; int r; r = a != 0 && 10 / a > 1; print(r);"), ["0"])

    def test_constant_folding_matches(self):
        src = "int a; a = 2 * 3 + 4; print(a);"
        self.assertEqual(output(src, fold=True), output(src, fold=False))
        _, _, _, q = compile_source(src, fold=True)
        self.assertEqual(len(q), 2)  # a = 10 ; print a

    def test_undeclared_variable(self):
        with self.assertRaises(CompileError):
            compile_source("x = 1;")

    def test_redeclaration(self):
        with self.assertRaises(CompileError):
            compile_source("int a; int a;")

    def test_syntax_error(self):
        with self.assertRaises(CompileError):
            compile_source("int a; a = ;")


if __name__ == "__main__":
    unittest.main()
