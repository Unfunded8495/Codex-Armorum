# TRAPS.md - classic reasoning traps, read the matching section on demand (CODE.md C7)

Format: WRONG assumption -> RIGHT rule. If you are writing code in one of these categories, read its table first and state which row applies.

## T1. Dates and times
| WRONG | RIGHT |
|---|---|
| JS `new Date().getMonth()` returns 1-12 | It returns 0-11. `getDate()` is 1-31, `getDay()` is weekday 0-6 |
| `datetime.now()` is comparable with UTC timestamps | Naive vs aware datetimes do not mix. Store UTC, convert at the edge |
| Adding 24h always advances one calendar day | DST breaks this. Use date arithmetic for days, not seconds |
| Date strings compare correctly | Only ISO-8601 zero-padded strings sort correctly. `"9/12/2025"` does not |
| `YYYY-MM-DD` parsed by JS `new Date()` is local | It is parsed as UTC midnight; with a local getter it can show the previous day |

## T2. Epochs
| WRONG | RIGHT |
|---|---|
| All epoch timestamps are seconds | JS `Date.now()` is milliseconds; Python `time.time()` is seconds. A 13-digit number is ms |
| SQLite stores datetimes | SQLite has no datetime type. Decide text-ISO or integer-epoch per column and never mix |

## T3. Mutation vs copy
| WRONG | RIGHT |
|---|---|
| `b = a` copies a list/dict | It aliases. Use `a.copy()`, `list(a)`, `dict(a)`, or `copy.deepcopy` for nesting |
| `list.sort()` / `.reverse()` return the list | They return None and mutate in place. `sorted()` / `reversed()` return new |
| `def f(x, acc=[])` gives a fresh list per call | Mutable defaults persist across calls. Use `acc=None` then `acc = acc or []` |
| Slicing a dict of lists copies the inner lists | Shallow copies share nested objects |
| Iterating a collection while removing from it is fine | It skips or errors. Iterate a copy or build a new collection |

## T4. Async
| WRONG | RIGHT |
|---|---|
| Calling an async function runs it | Without `await` you get a coroutine/promise object, often truthy, silently unrun |
| `forEach(async ...)` awaits each item | It does not. Use `for...of` with await, or `Promise.all(items.map(...))` |
| fetch errors throw on HTTP 404/500 | fetch only rejects on network failure. Check `resp.ok` |

## T5. Floats and money
| WRONG | RIGHT |
|---|---|
| `0.1 + 0.2 == 0.3` | False. Never compare floats with ==; use a tolerance |
| Store prices as floats | Store integer pence/cents or `decimal.Decimal`. Format at display only |
| `round()` is round-half-up | Python 3 rounds half to even: `round(2.5) == 2` |

## T6. Sorting
| WRONG | RIGHT |
|---|---|
| Default sort is numeric | JS default `sort()` is lexicographic: `[10, 9, 2]` sorts to `[10, 2, 9]`. Pass a comparator |
| Sorting handles None/mixed types | Python 3 raises on mixed comparisons. Key-function around None first |
| "Sort descending" means reverse every key | Multi-key sorts may need per-key direction: negate numerics or chain stable sorts |

## T7. Division and modulo
| WRONG | RIGHT |
|---|---|
| `%` behaves the same everywhere | Python `-7 % 3 == 2`; JS `-7 % 3 == -1`. Sign follows different operands |
| `/` is the same in both | Python `/` is float, `//` floors (toward negative infinity). JS `/` is float; `Math.trunc` vs `Math.floor` differ on negatives |

## T8. Regex
| WRONG | RIGHT |
|---|---|
| `.` matches newline | Not without DOTALL/s flag |
| `.*` takes the smallest match | Greedy by default; `.*?` is lazy |
| An unescaped `.` in a literal is fine | It matches anything: `"1.99"` matches `"1x99"` |
| `re.match` searches the whole string | It anchors at the start. `re.search` scans; `fullmatch` requires all |
| `^` and `$` are per-line | Only with MULTILINE/m |

## T9. Familiar-API lookalikes
| WRONG | RIGHT |
|---|---|
| Python has `.push()` / JS has `.append()` | Python `append`, JS `push`. `len(x)` vs `x.length` |
| `str.replace` behaves the same | Python replaces all occurrences; JS string replace does the FIRST only unless regex /g or `replaceAll` |
| Negative indexing works in JS | `arr[-1]` is undefined in JS. Use `arr.at(-1)` |
| `slice(a, b)` includes b | End-exclusive in both languages |
| SQLite enforces column types | It does not (dynamic typing), and it has no boolean: 0/1 integers by convention |

## T10. Closures
| WRONG | RIGHT |
|---|---|
| A loop-defined lambda captures the loop value | It captures the variable: all closures see the final value. Bind with a default arg (`lambda i=i:`) or `let` in JS |

## T11. Truthiness and equality
| WRONG | RIGHT |
|---|---|
| `if x:` means "x was provided" | 0, "", [], {} are falsy. Use `if x is not None:` when 0/empty are valid |
| `is` compares values | `is` is identity. Use `==` for values, `is` only for None/True/False singletons |
| JS `==` is safe enough | `"" == 0` is true. Always `===` |
| `if a == b == c` works in JS like Python | JS chains as `(a == b) == c`, comparing a boolean to c |

## T12. SQL
| WRONG | RIGHT |
|---|---|
| f-string values into SQL | Always parameterise (`?` placeholders). No exceptions, including "trusted" internal values |
| `col = NULL` finds nulls | NULL compares as unknown. Use `IS NULL` / `IS NOT NULL` |
| `NOT IN (subquery)` is safe with NULLs | One NULL in the subquery empties the result. Filter nulls or use NOT EXISTS |
| Row order without ORDER BY is stable | It is undefined. Never depend on it |
