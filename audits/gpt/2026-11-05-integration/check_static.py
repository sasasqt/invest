"""Authored audit checks: parse repository text; never import or execute it."""
import ast,base64,fnmatch,gzip,hashlib,json,pathlib,subprocess
r=pathlib.Path(__file__).parent
meta=json.loads((r/'identities.json').read_text())
remote={x['path']:x for x in meta['tree']['tree'] if x['type']=='blob'}
verified=[]
for x in meta['sources']:
    data=(r/'source'/x['path']).read_bytes()
    blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
    assert blob==x['blob']==remote[x['path']]['sha'],x['path']
    verified.append({'path':x['path'],'git_blob':blob,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'lines':len(data.splitlines())})
protocol=[]
for x in meta['protocol']:
    data=base64.b64decode(x['content']);observed=hashlib.sha256(data).hexdigest()
    assert observed==x['expected'],x['key']
    protocol.append({'key':x['key'],'sha256':observed,'bytes':len(data),'verified':True})
t=ast.parse((r/'source/scripts/save_run.py').read_text())
constants={n.targets[0].id:ast.literal_eval(n.value) for n in t.body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id in ('REQUIRED','RECORD_GLOBS','CODE_MANIFESTS','MAX_FILE_BYTES')}
required=constants['REQUIRED'];patterns=constants['RECORD_GLOBS']
missing=[p for p in required if not any(fnmatch.fnmatchcase(p,pattern) for pattern in patterns)]
assert not missing
data=('date,value\n'+'2024-01-02,0.125\n'*80000).encode()
assert len(data)>constants['MAX_FILE_BYTES']
oracle=[]
for repeat in (1,2):
    packed=gzip.compress(data,mtime=0); recovered=gzip.decompress(packed)
    assert recovered==data and len(packed)<constants['MAX_FILE_BYTES']
    small=b'date,value\n2024-01-02,0.125\n';assert len(small)<=constants['MAX_FILE_BYTES']
    oracle.append({'repeat':repeat,'input_bytes':len(data),'stored_bytes':len(packed),'decompressed_sha256':hashlib.sha256(recovered).hexdigest(),'equal':True,'small_negative_control':'below threshold; unchanged identity'})
shell=[]
for p in sorted((r/'source/scripts').glob('*.sh')):
    done=subprocess.run(['bash','-n',str(p)],capture_output=True,text=True)
    assert done.returncode==0,done.stderr
    shell.append({'command':['bash','-n',p.name],'exit':done.returncode})
result={'source_sha':meta['sha'],'source_files':verified,'protocol':protocol,'required_paths':len(required),'all_required_have_copy_pattern':not missing,'code_manifests':constants['CODE_MANIFESTS'],'compression_oracle':oracle,'oracle_scope':'independent stdlib reversible encoding contract; not untouched save_run or workflow execution','shell_syntax':shell,'tracked_files':len(remote),'runtime_product_runs':0}
(r/'static-results.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('source_files','protocol')},indent=2))
