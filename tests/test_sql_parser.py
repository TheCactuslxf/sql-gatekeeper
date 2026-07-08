from sql_gatekeeper.services.sql_parser import SqlParser


def test_parser_extracts_tables_predicates_and_limit():
    parsed = SqlParser().parse(
        "select u.uid, u.user_name from user u join user u2 on u.uid = u2.uid where u.uid = '10001' limit 10"
    )

    assert parsed.sql_type == "select"
    assert len(parsed.tables) == 2
    assert parsed.tables[0].table_name == "user"
    assert parsed.tables[0].alias == "u"
    assert parsed.tables[1].alias == "u2"
    assert parsed.predicate_value("uid", qualifier="u") == "10001"
    assert parsed.has_limit is True


def test_parser_handles_subquery_table_references():
    parsed = SqlParser().parse(
        "select * from (select uid from user where uid = 10001) t join user u on t.uid = u.uid where u.uid = 10001"
    )

    table_names = [table.table_name for table in parsed.tables]
    assert table_names.count("user") == 2

