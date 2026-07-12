from sql_gatekeeper.bootstrap.meta import build_seed_plan


def test_build_seed_plan_contains_expected_reference_objects():
    plan = build_seed_plan()

    assert plan.datasource_codes == ["biz_user_db", "biz_order_db", "demo_redis"]
    assert plan.logical_tables == ["user", "order"]
    assert plan.policy_codes == ["default_select_guard"]

