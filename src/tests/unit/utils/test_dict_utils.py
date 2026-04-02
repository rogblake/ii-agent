from ii_agent.utils.dict_utils import drop_none


def test_drop_none_recursive_removes_nested_none_and_empty_dicts():
    data = {
        "a": 1,
        "b": None,
        "c": {
            "x": None,
            "y": 2,
            "z": {"only_none": None},
        },
    }

    assert drop_none(data, recursive=True) == {"a": 1, "c": {"y": 2}}


def test_drop_none_non_recursive_only_removes_top_level_none():
    data = {
        "a": 1,
        "b": None,
        "c": {"x": None, "y": 2},
    }

    assert drop_none(data, recursive=False) == {"a": 1, "c": {"x": None, "y": 2}}
