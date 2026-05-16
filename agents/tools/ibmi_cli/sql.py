"""Pure SQL builder functions for the IBM i CLI toolkit.

SECURITY: ``_escape_sql_literal`` is the single sanctioned escape
(Db2 rule — double single quotes). F-string interpolation into SQL
is prohibited in this codebase; every caller here builds SQL by
concatenation after escaping.
"""

from __future__ import annotations


def _escape_sql_literal(value: str) -> str:
    """Double single quotes — the Db2 SQL literal escape rule.

    The only sanctioned way to embed untrusted text into a SQL literal
    in this module; f-string interpolation into SQL is prohibited.
    """
    return value.replace("'", "''")


def qcmdexc_wrap(command: str) -> str:
    """Wrap a CL command for execution via QSYS2.QCMDEXC."""
    escaped = _escape_sql_literal(command)
    return "SELECT QSYS2.QCMDEXC('" + escaped + "') AS QCMDEXC_OK FROM SYSIBM.SYSDUMMY1"


def pase_call_wrap(pase_command: str) -> str:
    """Wrap a PASE shell command for the sample.pase_call UDTF."""
    escaped = _escape_sql_literal(pase_command)
    return "SELECT * FROM TABLE(sample.pase_call('" + escaped + "'))"


def services_info_query(filter_pattern: str | None) -> str:
    """Build a QSYS2.SERVICES_INFO discovery query, optional SERVICE_NAME LIKE."""
    base_select = "SELECT SERVICE_SCHEMA_NAME, SERVICE_NAME, SERVICE_CATEGORY, EXAMPLE FROM QSYS2.SERVICES_INFO "
    order_by = "ORDER BY SERVICE_SCHEMA_NAME, SERVICE_NAME"
    if filter_pattern:
        escaped = _escape_sql_literal(filter_pattern)
        return base_select + "WHERE SERVICE_NAME LIKE '" + escaped + "' " + order_by
    return base_select + order_by
