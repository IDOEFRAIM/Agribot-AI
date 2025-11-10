from qa import Workflow


def test_context_node_with_known_query():
    wf = Workflow("What is Agriconnect?")
    state = wf.qa_state()
    updated = wf.context_node(state)
    assert updated["context"] is not None
    assert isinstance(updated["context"], tuple)