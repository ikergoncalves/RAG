# A Tour of the Python Programming Language

Python is a high-level, general-purpose programming language created by Guido
van Rossum and first released in 1991. It emphasizes code readability and a
syntax that lets programmers express concepts in fewer lines than many other
languages. This overview summarizes widely known, factual features of the
language.

## Design philosophy

Python's guiding principles are captured in **PEP 20, "The Zen of Python"**,
which includes well-known aphorisms such as "Readability counts" and "There
should be one — and preferably only one — obvious way to do it." The language
favors explicitness and simplicity over cleverness, and its official style
guide, **PEP 8**, codifies conventions for naming, indentation, and layout.

Indentation is syntactically significant in Python: blocks are defined by their
indentation level rather than by braces. This enforces a consistent visual
structure across codebases.

## Core data types

Python provides a rich set of built-in types:

### Numbers and text

- **int**: arbitrary-precision integers, so they never overflow.
- **float**: double-precision floating-point numbers.
- **str**: immutable sequences of Unicode characters.

### Collections

- **list**: an ordered, mutable sequence, written with square brackets.
- **tuple**: an ordered, immutable sequence, written with parentheses.
- **dict**: a mapping of keys to values (a hash map), written with braces.
- **set**: an unordered collection of unique elements.

The distinction between mutable types (list, dict, set) and immutable types
(int, float, str, tuple) is fundamental: only immutable, hashable values can be
used as dictionary keys or set members.

## Functions and comprehensions

Functions are defined with the `def` keyword and are first-class objects: they
can be passed as arguments, returned from other functions, and stored in data
structures. Python also supports anonymous functions via `lambda`.

**Comprehensions** offer a concise way to build collections. A list
comprehension such as `[x * x for x in range(10) if x % 2 == 0]` reads almost
like the mathematical set-builder notation it resembles, and there are
equivalent dictionary and set comprehensions.

## The standard library and ecosystem

Python ships with a large standard library — often described as "batteries
included" — covering tasks from file handling and JSON parsing to HTTP servers
and concurrency. Beyond the standard library, the Python Package Index (PyPI)
hosts hundreds of thousands of third-party packages installable with `pip`.

This combination of a readable core language, a comprehensive standard library,
and a vast package ecosystem explains why Python is widely used in web
development, data analysis, scientific computing, automation, and machine
learning.

## Exceptions and error handling

Python uses exceptions to signal errors. Code that may fail is wrapped in a
`try` block, with `except` clauses handling specific exception types, an
optional `else` clause for the success path, and a `finally` clause for cleanup
that must always run. Raising a specific exception type, rather than returning
an error code, keeps the normal flow of a program clear and pushes error
handling to the place best equipped to deal with it.
