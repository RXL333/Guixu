"""Validate the design bundle, not an implemented application.
Requires Python 3.12+ and jsonschema. No network or user-directory access.
"""
from __future__ import annotations
import copy,json,re,sqlite3,sys,uuid
from collections import Counter
from pathlib import Path
from jsonschema import Draft202012Validator,FormatChecker,ValidationError
ROOT=Path(__file__).resolve().parents[1]
checks=[]
def check(name,condition,details=''):
 checks.append({'name':name,'status':'PASS' if condition else 'FAIL','details':str(details)})
def load(path):return json.loads((ROOT/path).read_text(encoding='utf-8'))
def fails_validator(v,x):
 try:v.validate(x);return False
 except ValidationError:return True
schemas={p.name.removesuffix('.schema.json'):json.loads(p.read_text()) for p in (ROOT/'contracts/schemas').glob('*.json')}
for name,s in schemas.items():
 try:Draft202012Validator.check_schema(s);check('schema:'+name,True)
 except Exception as e:check('schema:'+name,False,e)
for p in ROOT.rglob('*.json'):
 if p.name=='validation-results.json':continue
 try:json.loads(p.read_text());check('json:'+str(p.relative_to(ROOT)),True)
 except Exception as e:check('json:'+str(p.relative_to(ROOT)),False,e)
settings=load('seed/default-settings.json');vs=Draft202012Validator(schemas['task-settings'],format_checker=FormatChecker())
check('defaults:complete_schema',not list(vs.iter_errors(settings)))
for name,mutation in [('depth_4',{'max_depth':4}),('invalid_engine',{'classification_mode':'magic'}),('rule_only_auto',{'classification_mode':'rules_only','classification_source':'auto_plan'}),('rename_enabled',{'allow_file_rename':True}),('extra_key',{'allow_overwrite':True})]:
 x=copy.deepcopy(settings);x.update(mutation);check('negative_settings:'+name,fails_validator(vs,x))
for depth in (1,2,3):
 x=copy.deepcopy(settings);x['max_depth']=depth;check(f'positive_settings:depth_{depth}',not list(vs.iter_errors(x)))
templates=load('seed/templates.json')['templates'];vt=Draft202012Validator(schemas['template'],format_checker=FormatChecker())
check('templates:count_24',len(templates)==24);check('templates:unique_ids',len({x['template_id'] for x in templates})==len(templates))
node_count=0
for t in templates:
 tid=t['template_id'];check('template_schema:'+tid,not list(vt.iter_errors(t)))
 nodes={n['category_id']:n for n in t['nodes']};node_count+=len(nodes)
 check('template_unique_nodes:'+tid,len(nodes)==len(t['nodes']))
 ok=True;depths=[]
 for key,n in nodes.items():
  seen=set();cur=key;d=0
  while cur is not None:
   if cur in seen or cur not in nodes:ok=False;break
   seen.add(cur);d+=1;cur=nodes[cur]['parent_id']
  depths.append(d)
 check('template_acyclic:'+tid,ok)
 check('template_depth:'+tid,ok and max(depths)<=t['minimum_depth']<=3)
 siblings=Counter(n['parent_id'] for n in nodes.values())
 check('template_siblings:'+tid,max(siblings.values())<=settings['max_siblings'])
 check('template_total_nodes:'+tid,len(nodes)<=settings['max_nodes_per_scope'])
 check('template_fallback_or_exhaustive:'+tid, (sum(bool(n['is_fallback']) for n in nodes.values())>=1) if t['requires_ai'] else set(nodes)=={'universal.types.'+x for x in ['image','text','pdf','word','slides','sheet','audio','video']})
 check('template_examples:'+tid,len(t['examples']['positive'])>=2 and len(t['examples']['negative'])>=1)
check('template_T24_no_AI',next(t for t in templates if t['template_id']=='universal.types')['requires_ai'] is False)
# Model result positive and negative contract fixtures.
v=Draft202012Validator(schemas['classification-result'],format_checker=FormatChecker())
result={'file_id':str(uuid.UUID(int=1)),'taxonomy_id':str(uuid.UUID(int=2)),'category_id':'universal.types.pdf','abstain':False,'model_score':.8,'evidence_ids':['e1'],'reason':'正文与文档类型一致。','tags':[],'warnings':[]}
check('classification:valid',not list(v.iter_errors(result)))
for name,mutation in [('path_escape_field',{'target_path':'C:\\Windows'}),('score_above_1',{'model_score':1.2}),('abstain_with_category',{'abstain':True}),('missing_evidence',{'evidence_ids':[]}),('null_category_no_abstain',{'category_id':None})]:
 x=copy.deepcopy(result);x.update(mutation);check('classification_reject:'+name,fails_validator(v,x))
abstain=copy.deepcopy(result);abstain.update(category_id=None,abstain=True,model_score=None,evidence_ids=[])
check('classification:valid_abstain',not list(v.iter_errors(abstain)))
# OpenAPI graph integrity (not a full third-party spec certification).
api=load('contracts/openapi.json');refs=[]
def walk(x):
 if isinstance(x,dict):
  if '$ref' in x:refs.append(x['$ref'])
  for v in x.values():walk(v)
 elif isinstance(x,list):
  for v in x:walk(v)
walk(api)
for ref in set(refs):
 valid=ref.startswith('#/');cur=api
 try:
  for part in ref[2:].split('/'):cur=cur[part.replace('~1','/').replace('~0','~')]
 except (KeyError,TypeError):valid=False
 check('openapi_ref:'+ref,valid)
opids=[];operation_count=0
for path,methods in api['paths'].items():
 for method,op in methods.items():
  operation_count+=1;opids.append(op['operationId']);params=op.get('parameters',[])
  pathparams={x['name'] for x in params if x['in']=='path' and x.get('required')}
  check('openapi_path:'+method+':'+path,pathparams==set(re.findall(r'\{([^}]+)\}',path)))
  if method!='get':check('openapi_idempotency:'+method+':'+path,any(x['in']=='header' and x['name']=='Idempotency-Key' and x['required'] for x in params))
  check('openapi_security:'+method+':'+path,(op.get('security',api['security'])!=[]) or path in ['/health','/media/{ticket}'])
check('openapi_unique_operation_ids',len(set(opids))==len(opids))
check('openapi_no_raw_source_path_input','source_path' not in api['paths']['/tasks']['post']['requestBody']['content']['application/json']['schema']['properties'])
check('openapi_fixed_tree_input','fixed_tree' in api['paths']['/tasks']['post']['requestBody']['content']['application/json']['schema']['properties'])
# Execute the reference SQL and exercise representative constraints.
db=sqlite3.connect(':memory:');db.executescript((ROOT/'contracts/database.sql').read_text());db.execute('pragma foreign_keys=on')
tables=[x[0] for x in db.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'")]
check('sql:21_tables',len(tables)==21);check('sql:integrity',db.execute('pragma integrity_check').fetchone()[0]=='ok')
check('sql:foreign_keys_enabled',db.execute('pragma foreign_keys').fetchone()[0]==1)
def ins(table,vals):
 db.execute('insert into '+table+' ('+','.join(vals)+') values ('+','.join('?' for _ in vals)+')',list(vals.values()))
def rejected(name,table,vals):
 db.execute('savepoint negative')
 try:
  ins(table,vals);check(name,False,'invalid row accepted')
 except sqlite3.IntegrityError:check(name,True)
 finally:db.execute('rollback to negative');db.execute('release negative')
h='a'*64;now='2026-09-12T00:00:00Z'
base_task={'id':'task-a','name':'fixture','status':'DRAFT','phase':'SETUP','settings_json':'{}','settings_hash':h,'created_at':now,'updated_at':now}
ins('tasks',base_task);ins('tasks',{**base_task,'id':'task-b'})
ins('task_scopes',{'id':'scope-a','task_id':'task-a','kind':'root_loose','source_root':'fixture/source','destination_root':'fixture/target','display_name':'fixture'})
file={'id':'file-a','task_id':'task-a','scope_id':'scope-a','original_path':'fixture/source/a.txt','current_path':'fixture/source/a.txt','path_key':'a.txt','relative_path':'a.txt','basename':'a.txt','extension':'.txt','modality':'text','size_bytes':4,'mtime_ns':1,'scan_status':'eligible','created_at':now,'updated_at':now}
ins('files',file)
rejected('sql_reject:cross_task_scope','files',{**file,'id':'file-b','task_id':'task-b'})
rejected('sql_reject:negative_size','files',{**file,'id':'file-c','path_key':'c.txt','size_bytes':-1})
rejected('sql_reject:duplicate_path','files',{**file,'id':'file-d'})
rejected('sql_reject:invalid_task_status','tasks',{**base_task,'id':'task-c','status':'DONE_WHATEVER'})
rejected('sql_reject:invalid_json','tasks',{**base_task,'id':'task-d','settings_json':'not-json'})
ins('taxonomies',{'id':'tax-a','task_id':'task-a','scope_id':'scope-a','version':1,'source':'template','status':'approved','tree_hash':h,'created_at':now})
cat={'taxonomy_id':'tax-a','category_id':'text','parent_id':None,'name':'Text','path_segments_json':'["Text"]','depth':1,'ordinal':0,'definition_json':'{}','selectable':1}
ins('categories',cat);rejected('sql_reject:depth_4','categories',{**cat,'category_id':'bad','depth':4})
cl={'id':'cl-a','task_id':'task-a','file_id':'file-a','taxonomy_id':'tax-a','category_id':'text','attempt':1,'source':'rule','model_score':None,'review_band':'high','abstain':0,'reason':'fixture','evidence_refs_json':'[]','warnings_json':'[]','input_hash':h,'created_at':now}
ins('classifications',cl);rejected('sql_reject:abstain_inconsistency','classifications',{**cl,'id':'cl-b','attempt':2,'abstain':1})
plan={'id':'plan-a','task_id':'task-a','version':1,'plan_hash':h,'status':'approved','operation_mode':'copy','settings_hash':h,'taxonomy_hashes_json':'[]','source_snapshot_hash':h,'summary_json':'{}','created_at':now}
ins('plans',plan);rejected('sql_reject:undo_without_parent','plans',{**plan,'id':'plan-b','version':2,'plan_hash':'b'*64,'plan_kind':'undo'})
op={'id':'op-a','plan_id':'plan-a','file_id':'file-a','ordinal':0,'action':'copy','source_path':'fixture/source/a.txt','target_path':'fixture/target/a.txt','target_key':'fixture/target/a.txt','source_snapshot_json':'{}','expected_sha256':h,'state':'PLANNED','updated_at':now}
ins('operations',op);rejected('sql_reject:duplicate_plan_file','operations',{**op,'id':'op-b','ordinal':1,'target_path':'another','target_key':'another'})
rejected('sql_reject:copy_without_hash','operations',{**op,'id':'op-c','expected_sha256':None})
check('sql:final_foreign_key_check',db.execute('pragma foreign_key_check').fetchall()==[])
db.close()
# Markdown links and required delivery artifacts.
for p in ROOT.rglob('*.md'):
 for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)',p.read_text()):
  if '://' in target or target.startswith('#'):continue
  clean=target.split('#',1)[0]
  if not clean:continue
  check('markdown_link:'+str(p.relative_to(ROOT))+':'+target,(p.parent/clean).exists())
required=['README.md','START_HERE.md','AGENTS.md','PROJECT_STATUS.md','ui/DESIGN_REFERENCE.html','contracts/openapi.json','prompts/codex/00_MASTER_GOAL.md','prompts/codex/01_FOUNDATION.md','prompts/codex/09_RELEASE.md']
for f in required:check('delivery:'+f,(ROOT/f).is_file())
check('goals:nine_stages',len([p for p in (ROOT/'prompts/codex').glob('*.md') if not p.name.startswith('00_')])==9)
check('model_prompt_count',len([p for p in (ROOT/'prompts/models').glob('*.md') if p.name[0].isdigit()])==6)
# Read existing HTML layout measurements if available; not a desktop integration test.
vp=ROOT/'reports/ui/viewport-checks.json'
if vp.exists():
 for x in json.loads(vp.read_text()):check('static_html_no_horizontal_overflow:'+str(x['width']),x['body']==x['width'] and x['root']==x['width'])
summary={'bundle_only':True,'application_tests_run':False,'schema_count':len(schemas),'template_count':len(templates),'category_nodes':node_count,'database_tables':len(tables),'api_operations':operation_count,'checks_total':len(checks),'passed':sum(x['status']=='PASS' for x in checks),'failed':sum(x['status']=='FAIL' for x in checks),'checks':checks}
(ROOT/'reports').mkdir(exist_ok=True)
(ROOT/'reports/validation-results.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in summary.items() if k!='checks'},ensure_ascii=False,indent=2))
for x in checks:
 if x['status']=='FAIL':print('FAIL:',x['name'],x['details'])
sys.exit(1 if summary['failed'] else 0)