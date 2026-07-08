import pytest

from sql_gatekeeper.services.precheck import BasicSqlGuard


@pytest.mark.parametrize(
    ("sql", "allowed", "reason_code"),
    [
        ("select * from user_1 where uid = 10001", True, "ALLOW"),
        ("select 1; select 2", False, "MULTI_STATEMENT"),
        ("update user_1 set status = 0 where uid = 10001", False, "SQL_TYPE_DENIED"),
        ("/* test */ select * from user_1", False, "LEADING_COMMENT"),
        ("show tables", False, "UNSUPPORTED_SQL"),
    ],
)
def test_basic_sql_guard(sql, allowed, reason_code):
    decision = BasicSqlGuard().evaluate(sql)

    assert decision.allowed is allowed
    assert decision.reason_code == reason_code

