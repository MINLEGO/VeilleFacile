from veillefacile.keywords import Keywords, add, effective, regenerate, remove, replace


def test_effective_is_generated_minus_rejected_plus_manual_case_insensitive():
    k = Keywords(generated=["RAG", "Llama", "x"], manual=["rag", "Mine"], rejected=["X"])
    assert effective(k) == ["RAG", "Llama", "Mine"]


def test_remove_generated_rejects_it_and_manual_just_leaves():
    k = remove(remove(Keywords(generated=["a", "b"], manual=["c"]), "A"), "C")
    assert k.rejected == ["A"] and k.manual == []
    assert effective(k) == ["b"]


def test_add_rehabilitates_rejected():
    k = add(remove(Keywords(generated=["a"]), "a"), "A")
    assert k.rejected == [] and effective(k) == ["a"]


def test_replace_rejects_generated_absent_from_list():
    k = replace(Keywords(generated=["a", "b"]), ["B", "z"])
    assert k.manual == ["B", "z"] and k.rejected == ["a"]
    assert effective(k) == ["b", "z"]


def test_regenerate_keeps_manual_and_rejected():
    k = regenerate(Keywords(generated=["old"], manual=["m"], rejected=["bad"]), ["new", "bad"])
    assert k.generated == ["new", "bad"] and k.manual == ["m"] and k.rejected == ["bad"]
    assert effective(k) == ["new", "m"]
