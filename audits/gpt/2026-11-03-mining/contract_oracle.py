"""Trusted, stdlib-only contract arithmetic. Never imports product modules.
Results demonstrate expected invariants and a declared static trace model,
not behavior of the untouched installed repository."""
import json, math


def sum2(values, i):
    if i < 1 or values[i] is None or values[i-1] is None:
        return None
    return values[i-1] + values[i]


def run():
    closes = [4, 9, 16, 25, 36, 49]
    member = [False, True, False, False, True, True]
    full_abs = [abs(x) for x in closes]
    pre_masked = [x if m else None for x,m in zip(full_abs,member)]
    rows=[]
    for i in [1,4,5]:
        expected=sum2(full_abs,i)
        trace_model=sum2(pre_masked,i)
        rows.append({'i':i,'expected_full_history_abs_sum':expected,'premasked_trace_model':trace_model})
    assert rows == [{'i':1,'expected_full_history_abs_sum':13,'premasked_trace_model':None},{'i':4,'expected_full_history_abs_sum':61,'premasked_trace_model':None},{'i':5,'expected_full_history_abs_sum':85,'premasked_trace_model':85}]
    all_member=[sum2(full_abs,i) for i in [1,4,5]]
    assert all_member==[13,61,85]
    opens=[10,12,18,24,30,36]
    label_at_member_t1=opens[3]/opens[2]-1
    assert math.isclose(label_at_member_t1,1/3)
    assert not member[2] and not member[3]
    # Independent interval enumeration, not the repository split function.
    intervals=[]
    for n,k,h,e in [(100,60,1,0),(100,60,5,2),(12,8,2,1)]:
        allowed=[i for i in range(k) if i+1+h < k-e]
        assert all(i+1+h < k-e for i in allowed)
        if allowed:
            assert allowed[-1]+1+h==k-e-1
        intervals.append({'n':n,'k':k,'h':h,'embargo':e,'allowed_dev':allowed,'last_exit':allowed[-1]+1+h if allowed else None})
    return {'scope':'stdlib contract arithmetic / declared static trace model, not product execution','entry_reentry':rows,'all_member_control':all_member,'decision_member_future_nonmember_label':label_at_member_t1,'independent_interval_enumeration':intervals}

if __name__ == '__main__':
    results=[run(),run()]
    assert results[0]==results[1]
    print(json.dumps({'repeats':2,'same_result':True,'results':results},indent=2))

