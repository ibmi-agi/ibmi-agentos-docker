# IBM i conventions reference

Read at search time by every agent. Treat this like a PR review comment, not a tutorial.

## Library / schema namespacing

- `QSYS` — operating system objects (programs, commands). Avoid querying directly unless inspecting OS state.
- `QSYS2` — IBM-supplied SQL catalog views and services (UDTFs). The canonical landing zone for system-state queries: `ACTIVE_JOB_INFO`, `SYSTEM_STATUS_INFO`, `SYSTABLES`, `SYSCOLUMNS`, `OBJECT_STATISTICS`, etc.
- `SYSTOOLS` — IBM-supplied utility procedures and views. Less stable across TR levels than `QSYS2`; check `LIST_PRODUCT_INFO` if a procedure is missing.
- `QGPL` — general-purpose library, often where customers put ad-hoc objects.
- Customer libraries — uppercase, max 10 characters native, often shorter than the SQL alias.

## Db2 for i SQL dialect

- **`FETCH FIRST N ROWS ONLY`**, not `LIMIT`. The query optimizer treats this as a constraint and can short-circuit accordingly.
- **`UPPER()`** for case-insensitive string comparisons on EBCDIC columns. Don't rely on `LOWER()` parity — works but slower.
- **Fully qualified names** (`SCHEMA.TABLE`). Native objects can use 3-part `SCHEMA.TABLE.MEMBER` for multi-member physical files, but for SQL work stick to two-part.
- **Fixed-width `CHAR` columns are space-padded**. `TRIM(col)` before comparing or grouping.
- **EBCDIC sort order** is not ASCII. `'a' < 'A'` is true on EBCDIC. Sort with `ORDER BY UPPER(col)` when alphabetic order matters.

## Job naming

Job identity is the three-part name `number/user/name`:

- `number` — system-assigned 6-digit job number
- `user` — user profile that started the job
- `name` — the job name itself (often `QPADEV*`, `QZDASOINIT`, custom names)

When a tool requires a job spec, **always supply the full three-part form** — system functions like `JOBLOG_INFO(JOB_NAME => '123456/QUSER/QPADEV0001')` are unambiguous only with all three.

## Authorities

- `*PUBLIC` is the catch-all profile representing "everyone not otherwise listed". `*PUBLIC *EXCLUDE` is the most restrictive baseline.
- Object authority levels in order of permissiveness: `*USE` < `*CHANGE` < `*ALL`. `*USE` is "read and run", `*CHANGE` adds writes, `*ALL` adds delete/grant/own.
- Special authorities (system-wide): `*ALLOBJ` (all-object access), `*SECADM` (security admin), `*SAVSYS` (save/restore), `*IOSYSCFG` (TCP/IP and config), `*JOBCTL` (job control).
- A user with `*ALLOBJ` bypasses object-level authority — flag this on audits.

## Performance gotchas

- `QSYS2.SYSTABLES.NUMBER_ROWS` is **statistics-based**, not exact. For correctness use `SELECT COUNT(*)`; for ranking use `NUMBER_ROWS` and accept the imprecision.
- `QSYS2.ACTIVE_JOB_INFO.CPU_PERCENTAGE` is **since-job-start**. Use `ELAPSED_CPU_PERCENTAGE` after `RESET_STATISTICS` for true instantaneous readings.
- Tech Refresh level **changes which columns exist** on system catalog views. Don't assume columns from training data — always `describe_sql_object` first.

## Result-set hygiene

- Default to 100-row bounded queries unless the user explicitly asks for more.
- Summarize large datasets; offer to show details on request rather than dumping.
- Always show the SQL before executing destructive operations.
