from sql_gatekeeper.services.sql_parser import SqlParser
from sql_gatekeeper.services.sql_rewrite import SqlRewriteEngine, TableRewritePlan


def test_rewrite_engine_replaces_table_tokens_by_span():
    sql = "select * from user u join user u2 on u.uid = u2.uid where u.uid = 10001"
    parsed = SqlParser().parse(sql)

    plans = [
        TableRewritePlan(
            original_table_name="user",
            physical_table_name="user_1",
            token_start=parsed.tables[0].token_start,
            token_end=parsed.tables[0].token_end,
        ),
        TableRewritePlan(
            original_table_name="user",
            physical_table_name="user_1",
            token_start=parsed.tables[1].token_start,
            token_end=parsed.tables[1].token_end,
        ),
    ]

    rewritten = SqlRewriteEngine().rewrite(parsed, plans)
    assert rewritten == "select * from user_1 u join user_1 u2 on u.uid = u2.uid where u.uid = 10001"


def test_rewrite_engine_rewrites_time_shard_table_name():
    sql = "select * from order where order_id = 'A1002' limit 10"
    parsed = SqlParser().parse(sql)

    plans = [
        TableRewritePlan(
            original_table_name="order",
            physical_table_name="order_2025_07",
            token_start=parsed.tables[0].token_start,
            token_end=parsed.tables[0].token_end,
        )
    ]

    rewritten = SqlRewriteEngine().rewrite(parsed, plans)
    assert rewritten == "select * from order_2025_07 where order_id = 'A1002' limit 10"


def test_rewrite_engine_rewrites_multi_alias_to_different_shards():
    sql = "select * from user u join user v on u.uid <> v.uid where u.uid = '10000' and v.uid = '10001'"
    parsed = SqlParser().parse(sql)

    plans = [
        TableRewritePlan(
            original_table_name="user",
            physical_table_name="user_0",
            token_start=parsed.tables[0].token_start,
            token_end=parsed.tables[0].token_end,
        ),
        TableRewritePlan(
            original_table_name="user",
            physical_table_name="user_1",
            token_start=parsed.tables[1].token_start,
            token_end=parsed.tables[1].token_end,
        ),
    ]

    rewritten = SqlRewriteEngine().rewrite(parsed, plans)
    assert rewritten == "select * from user_0 u join user_1 v on u.uid <> v.uid where u.uid = '10000' and v.uid = '10001'"
