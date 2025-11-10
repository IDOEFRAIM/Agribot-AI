from qa import Workflow


def test(query):
    workflow = Workflow(query)

    state = workflow.qa_state()
    final_state,time_to_reply = workflow.qa_reply(state)
    return final_state,time_to_reply 

final_state,time_to_reply  = test("quel culture me conseilles tu")
print(final_state,time_to_reply)