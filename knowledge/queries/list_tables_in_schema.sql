-- <query list_tables_in_schema>
-- <description>List all base tables and views in a given schema, ordered by row count.</description>
-- <parameters>
--   schema_name: SQL name of the library (default 'QGPL')
--   limit: FETCH FIRST N rows (default 50)
-- </parameters>
-- <notes>
--   Filters TABLE_TYPE to 'T' (table) and 'V' (view) — excludes aliases
--   and physical files that aren't usually interesting in exploration.
--   ORDER BY NUMBER_ROWS DESC surfaces the meatiest objects first;
--   note NUMBER_ROWS is statistics-based and may be 0 for fresh tables.
-- </notes>
-- <query>
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    TABLE_TYPE,
    NUMBER_ROWS,
    LAST_USED_TIMESTAMP
FROM QSYS2.SYSTABLES
WHERE TABLE_SCHEMA = UPPER(:schema_name)
  AND TABLE_TYPE IN ('T', 'V')
ORDER BY NUMBER_ROWS DESC NULLS LAST
FETCH FIRST :limit ROWS ONLY
-- </query>
