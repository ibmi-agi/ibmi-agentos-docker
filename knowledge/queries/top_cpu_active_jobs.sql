-- <query top_cpu_active_jobs>
-- <description>Top N active jobs by CPU percentage. Use to spot runaway workloads.</description>
-- <parameters>
--   subsystem: optional subsystem filter; pass '%' for all (default '%')
--   limit: FETCH FIRST N rows (default 20)
-- </parameters>
-- <notes>
--   CPU_PERCENTAGE is since-job-activation. For instantaneous CPU
--   pressure you want ELAPSED_CPU_PERCENTAGE after a RESET_STATISTICS
--   call — that's a different pattern, two-step.
--   Filters out system jobs (JOB_TYPE = 'SYS') and subsystem monitors
--   (JOB_TYPE = 'SBS') so the result is the workload you can actually
--   intervene on.
-- </notes>
-- <query>
SELECT
    JOB_NAME,
    SUBSYSTEM,
    JOB_TYPE,
    CPU_PERCENTAGE,
    TEMPORARY_STORAGE,
    RUN_PRIORITY
FROM TABLE(QSYS2.ACTIVE_JOB_INFO()) AJI
WHERE JOB_TYPE NOT IN ('SYS', 'SBS')
  AND SUBSYSTEM LIKE UPPER(:subsystem)
ORDER BY CPU_PERCENTAGE DESC
FETCH FIRST :limit ROWS ONLY
-- </query>
