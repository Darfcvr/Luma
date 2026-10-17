from pathlib import Path
import json,re,time

def load_json(path,default=None):
    p=Path(path)
    if not p.exists(): return default
    try: return json.loads(p.read_text(encoding='utf-8'))
    except Exception: return default

def save_json(path,data):
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(p.suffix+'.tmp'); tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8'); tmp.replace(p)

def clean_llm_text(text):
    text=(text or '').strip(); text=re.sub(r'^```(?:text|txt)?\s*','',text,flags=re.I); text=re.sub(r'\s*```$','',text); text=re.sub(r'^(final prompt|prompt)\s*:\s*','',text,flags=re.I); return text.strip()

def now(): return time.strftime('%Y-%m-%d %H:%M:%S')
