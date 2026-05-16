-- Reusable example queries against the Db2 for i SAMPLE schema.
-- Each query is headed with a name / description / tables block.
-- Use ? placeholders where a value is meant to be parameterized;
-- otherwise constants are fine for illustration.

-- name: employee_by_empno
-- description: Look up a single employee by EMPNO. EMPNO is CHAR(6), left-padded with zeros (e.g. '000010').
-- tables: EMPLOYEE
SELECT EMPNO, FIRSTNME, MIDINIT, LASTNAME, WORKDEPT, JOB, HIREDATE, SALARY
FROM SAMPLE.EMPLOYEE
WHERE EMPNO = ?
FETCH FIRST 1 ROWS ONLY;

-- name: employees_by_department
-- description: List employees in a given department, joined to the department name. WORKDEPT is CHAR(3).
-- tables: EMPLOYEE, DEPARTMENT
SELECT E.EMPNO, E.FIRSTNME, E.LASTNAME, E.JOB, D.DEPTNAME
FROM SAMPLE.EMPLOYEE E
JOIN SAMPLE.DEPARTMENT D ON D.DEPTNO = E.WORKDEPT
WHERE E.WORKDEPT = ?
ORDER BY E.LASTNAME, E.FIRSTNME
FETCH FIRST 100 ROWS ONLY;

-- name: average_salary_by_department
-- description: Average salary per department, ordered descending. CAST is defensive against DECIMAL(9,2) overflow.
-- tables: EMPLOYEE, DEPARTMENT
SELECT D.DEPTNO, D.DEPTNAME,
       COUNT(*) AS HEADCOUNT,
       CAST(AVG(E.SALARY) AS DECIMAL(11,2)) AS AVG_SALARY
FROM SAMPLE.EMPLOYEE E
JOIN SAMPLE.DEPARTMENT D ON D.DEPTNO = E.WORKDEPT
WHERE E.SALARY IS NOT NULL
GROUP BY D.DEPTNO, D.DEPTNAME
ORDER BY AVG_SALARY DESC
FETCH FIRST 50 ROWS ONLY;

-- name: manager_direct_reports
-- description: Given a manager's EMPNO, list their direct reports — i.e. all employees in any department they manage.
-- tables: DEPARTMENT, EMPLOYEE
SELECT D.DEPTNO, D.DEPTNAME, E.EMPNO, E.FIRSTNME, E.LASTNAME, E.JOB
FROM SAMPLE.DEPARTMENT D
JOIN SAMPLE.EMPLOYEE E ON E.WORKDEPT = D.DEPTNO
WHERE D.MGRNO = ?
ORDER BY D.DEPTNO, E.LASTNAME
FETCH FIRST 200 ROWS ONLY;

-- name: employees_on_project
-- description: List every employee assigned to a given project, with their activity description.
-- tables: EMP_ACT, EMPLOYEE, ACT, PROJECT
SELECT P.PROJNO, P.PROJNAME,
       E.EMPNO, E.FIRSTNME, E.LASTNAME,
       A.ACTKWD, A.ACTDESC,
       EA.EMPTIME, EA.EMSTDATE, EA.EMENDATE
FROM SAMPLE.EMP_ACT EA
JOIN SAMPLE.EMPLOYEE E ON E.EMPNO = EA.EMPNO
JOIN SAMPLE.PROJECT  P ON P.PROJNO = EA.PROJNO
JOIN SAMPLE.ACT      A ON A.ACTNO = EA.ACTNO
WHERE EA.PROJNO = ?
ORDER BY E.LASTNAME, EA.EMSTDATE
FETCH FIRST 200 ROWS ONLY;

-- name: activity_breakdown_by_employee
-- description: For one employee, show how their time has been split across activities. EMPTIME is fraction of their time.
-- tables: EMP_ACT, ACT
SELECT EA.EMPNO,
       A.ACTKWD, A.ACTDESC,
       COUNT(*) AS ASSIGNMENTS,
       CAST(SUM(COALESCE(EA.EMPTIME, 0)) AS DECIMAL(8,2)) AS TOTAL_EMPTIME
FROM SAMPLE.EMP_ACT EA
JOIN SAMPLE.ACT A ON A.ACTNO = EA.ACTNO
WHERE EA.EMPNO = ?
GROUP BY EA.EMPNO, A.ACTKWD, A.ACTDESC
ORDER BY TOTAL_EMPTIME DESC
FETCH FIRST 50 ROWS ONLY;

-- name: departments_without_manager
-- description: Departments where MGRNO is NULL — useful for data-completeness checks.
-- tables: DEPARTMENT
SELECT DEPTNO, DEPTNAME, ADMRDEPT, LOCATION
FROM SAMPLE.DEPARTMENT
WHERE MGRNO IS NULL
ORDER BY DEPTNO
FETCH FIRST 50 ROWS ONLY;

-- name: projects_ending_this_year
-- description: Projects whose planned end date falls within the current calendar year.
-- tables: PROJECT
SELECT PROJNO, PROJNAME, DEPTNO, RESPEMP, PRSTDATE, PRENDATE
FROM SAMPLE.PROJECT
WHERE PRENDATE IS NOT NULL
  AND YEAR(PRENDATE) = YEAR(CURRENT DATE)
ORDER BY PRENDATE
FETCH FIRST 100 ROWS ONLY;

-- name: total_emptime_per_project
-- description: Total assigned EMPTIME per project, joined to the project name.
-- tables: EMP_ACT, PROJECT
SELECT P.PROJNO, P.PROJNAME,
       COUNT(DISTINCT EA.EMPNO) AS DISTINCT_EMPLOYEES,
       CAST(SUM(COALESCE(EA.EMPTIME, 0)) AS DECIMAL(10,2)) AS TOTAL_EMPTIME
FROM SAMPLE.EMP_ACT EA
JOIN SAMPLE.PROJECT P ON P.PROJNO = EA.PROJNO
GROUP BY P.PROJNO, P.PROJNAME
ORDER BY TOTAL_EMPTIME DESC
FETCH FIRST 100 ROWS ONLY;

-- name: department_hierarchy
-- description: Walk the department tree from a root down using the self-referential ADMRDEPT column.
-- tables: DEPARTMENT
WITH DEPT_TREE (DEPTNO, DEPTNAME, ADMRDEPT, LVL) AS (
    SELECT DEPTNO, DEPTNAME, ADMRDEPT, 1
    FROM SAMPLE.DEPARTMENT
    WHERE DEPTNO = ?           -- root department to start from
    UNION ALL
    SELECT D.DEPTNO, D.DEPTNAME, D.ADMRDEPT, T.LVL + 1
    FROM SAMPLE.DEPARTMENT D
    JOIN DEPT_TREE T ON D.ADMRDEPT = T.DEPTNO
    WHERE D.DEPTNO <> D.ADMRDEPT    -- guard against the root self-reference
      AND T.LVL < 10
)
SELECT LVL, DEPTNO, DEPTNAME, ADMRDEPT
FROM DEPT_TREE
ORDER BY LVL, DEPTNO
FETCH FIRST 200 ROWS ONLY;
