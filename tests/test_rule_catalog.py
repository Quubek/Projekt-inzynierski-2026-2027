from pathlib import Path

from streamlit.testing.v1 import AppTest

from log_analyzer.contracts import RuleDefinition
from log_analyzer.dashboard import rule_catalog
from test_dashboard import mock_api


APP = Path(__file__).resolve().parents[1] / "src/log_analyzer/dashboard/app.py"


def test_home_catalog_navigation_and_search_do_not_require_api(monkeypatch):
    api = mock_api(monkeypatch)
    page = AppTest.from_file(str(APP), default_timeout=15).run()
    assert not page.exception and page.title[0].value == "Analizator logów"
    assert not page.get("popover")
    assert not any(" / " in item.value for item in page.caption)
    page.button(key="open_rule_catalog").click().run()
    assert not page.exception and page.title[0].value == "Katalog reguł"
    assert any(item.value == "HDFS-001" for item in page.text)
    page.text_input(key="rule_catalog_search").set_value("hdfs-003").run()
    assert any(item.value == "HDFS-003" for item in page.text)
    assert not any(item.value == "HDFS-001" for item in page.text)
    page.text_input(key="rule_catalog_search").set_value("nieistniejąca reguła").run()
    assert page.info
    page.button(key="back_to_home").click().run()
    assert page.title[0].value == "Analizator logów" and not page.exception
    api.history.assert_not_called()
    api.report.assert_not_called()


def test_catalog_pagination_and_search_reset_page(monkeypatch):
    rules = {f"TEST-{index:03}": RuleDefinition(rule_id=f"TEST-{index:03}", version="test",
                                               name=f"Reguła {index}", description=f"Warunek {index}.")
             for index in range(30)}
    monkeypatch.setattr(rule_catalog, "RULE_NAMES", rules)
    monkeypatch.setattr(rule_catalog, "rule_definition", rules.__getitem__)
    page = AppTest.from_file(str(APP), default_timeout=15)
    page.query_params["view"] = "rules"
    page.run()
    assert any(item.value == "TEST-000" for item in page.text)
    assert not any(item.value == "TEST-029" for item in page.text)
    page.number_input(key="rule_catalog_page").set_value(2).run()
    assert any(item.value == "TEST-029" for item in page.text)
    assert not any(item.value == "TEST-000" for item in page.text)
    page.text_input(key="rule_catalog_search").set_value("Warunek 0.").run()
    assert not page.exception and page.number_input(key="rule_catalog_page").value == 1
    assert any(item.value == "TEST-000" for item in page.text)
