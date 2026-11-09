import json

from prepare_experiment import examples
from run_experiment import score


def test_contract_requires_actual_source_evidence():
    source = {
        "id": "test-source",
        "context": "Dit is een bronzin met voldoende lengte. Een tweede bronzin.",
        "facts": ["Eerste feit.", "Tweede feit."],
        "missing_info_question": "Wat ontbreekt?",
    }
    row = examples(source)[0]
    assert score(row, json.dumps(row["target"]))["contract"]
    invented = {**row["target"], "bewijs": "Dit bewijs staat helemaal niet in de bron."}
    assert not score(row, json.dumps(invented))["contract"]
    assert not score(row, "Dit is geen JSON")["contract"]
    missing = examples(source)[-1]
    assert score(missing, json.dumps(missing["target"]))["contract"]
    assert not score(missing, json.dumps(row["target"]))["contract"]
