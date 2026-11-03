import json, math
from pathlib import Path

# Independently authored finite-list contract arithmetic; not repository execution.
def trailing_expected(xs, transform, width):
    out=[]
    for end in range(len(xs)):
        window=xs[max(0,end-width+1):end+1]
        out.append(sum(transform(x) for x in window) if len(window)==width and all(x is not None for x in window) else None)
    return out

def masked_trace(xs,members,transform,width):
    # Models the *statically observed* premature mask, not product code.
    ys=[transform(x) if m else None for x,m in zip(xs,members)]
    return trailing_expected(ys,lambda x:x,width)

def labels(opens,horizon,current_members):
    values=[]
    for t,m in enumerate(current_members):
        end=t+1+horizon
        entry=t+1
        if not m or end>=len(opens) or opens[entry] is None or opens[end] is None:
            values.append(None)
        else:
            values.append(opens[end]/opens[entry]-1)
    return values

rows=[]
prices=[4,9,16,25,36]
membership=[False,True,True,False,True]
for repeat in (1,2):
    transforms={"abs":abs,"neg":lambda x:-x,"log":math.log,"sign":lambda x:1 if x>0 else -1 if x<0 else 0}
    unary={}
    for name,fn in transforms.items():
        expected=trailing_expected(prices,fn,2)
        trace=masked_trace(prices,membership,fn,2)
        control=masked_trace(prices,[True]*len(prices),fn,2)
        assert control==expected
        assert trace[1] is None and trace[4] is None
        assert expected[1] is not None and expected[4] is not None
        unary[name]={"entry_expected":expected[1],"reentry_expected":expected[4],"entry_static_model":trace[1],"reentry_static_model":trace[4],"all_member_control":control}
    opens=[10,20,30,40,50,60]
    current=[True,True,False,False,True,True]
    # Future membership does not enter the definition for earlier t.
    future_changed=[True,True,True,True,False,False]
    before=labels(opens,2,current)
    after=labels(opens,2,future_changed)
    assert before[:2]==after[:2]
    assert math.isclose(before[0],1)
    assert math.isclose(before[1],2/3)
    missing=opens[:];missing[3]=None
    assert labels(missing,2,current)[0] is None
    # Derive allowed development decisions from the interval contract directly.
    purge=[]
    for k in (1,2,10,60):
      for h in (1,2,5):
       for embargo in (0,2):
        contract=[i for i in range(k) if i+1+h<k-embargo]
        cut=max(k-h-embargo-1,0)
        assert contract==list(range(cut))
        purge.append({"k":k,"h":h,"embargo":embargo,"last_dev_exit":contract[-1]+1+h if contract else None,"before":k-embargo})
    rows.append({"repeat":repeat,"unary":unary,"label_control":before,"future_membership_control_first2":after[:2],"missing_endpoint_control":labels(missing,2,current),"purge_cases":len(purge),"all_contract_controls":"passed"})
record={"kind":"trusted independent stdlib contract arithmetic, not untouched product runtime","product_imports":0,"source_sha":"9913f94b9b795bd9633a6a683e9f420301e400b3","repetitions":rows}
Path("/workspace/scratch/7e72cd5cc845/mining_verifier/oracle-result.json").write_text(json.dumps(record,indent=2),encoding="utf-8")
print(json.dumps(record))

