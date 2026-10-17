import json,time,requests,secrets
from pathlib import Path
class ComfyClient:
    def __init__(self,cfg,root='.'): self.base=cfg['base_url'].rstrip('/'); self.poll=cfg.get('poll_interval',1.0); self.timeout=cfg.get('timeout',3600); self.output_directory=cfg.get('output_directory',''); self.root=Path(root).resolve()
    def check(self): requests.get(self.base+'/system_stats',timeout=15).raise_for_status(); return True
    def load_workflow(self,path): return json.loads(Path(path).read_text(encoding='utf-8'))
    def set_prompt(self,wf,node_id,input_name,prompt):
        node=wf.get(str(node_id)) or wf.get(node_id)
        if node is None: raise KeyError(f'Workflow node {node_id} not found')
        node.setdefault('inputs',{})[input_name]=prompt
    def randomize_seeds(self,wf):
        randomized={}
        for node_id,node in wf.items():
            inputs=node.get('inputs',{})
            if node.get('class_type')=='KSampler' and 'seed' in inputs:
                inputs['seed']=secrets.randbelow(2**32-1)+1
                randomized[node_id]=inputs['seed']
            elif node.get('class_type')=='KSamplerAdvanced' and 'noise_seed' in inputs:
                inputs['noise_seed']=secrets.randbelow(2**32-1)+1
                randomized[node_id]=inputs['noise_seed']
        return randomized
    def queue(self,wf):
        r=requests.post(self.base+'/prompt',json={'prompt':wf,'client_id':'ai-image-agent'},timeout=30); r.raise_for_status(); d=r.json()
        if 'error' in d: raise RuntimeError(str(d))
        return d['prompt_id']
    def upload_image(self, path):
        image_path = Path(path)
        with image_path.open('rb') as image_file:
            response = requests.post(self.base + '/upload/image',
                files={'image': (image_path.name, image_file, 'image/png')},
                data={'overwrite': 'true'}, timeout=120)
        response.raise_for_status()
        payload = response.json()
        name = payload.get('name') or image_path.name
        subfolder = payload.get('subfolder', '')
        return f"{subfolder}/{name}" if subfolder else name
    def wait(self,pid,stop_event=None):
        start=time.time(); transient_errors=0
        while time.time()-start<self.timeout:
            if stop_event is not None and stop_event.is_set(): raise InterruptedError('Generation stopped by user')
            try:
                r=requests.get(self.base+'/history/'+pid,timeout=30); r.raise_for_status(); item=r.json().get(pid); transient_errors=0
            except requests.RequestException:
                transient_errors+=1
                if transient_errors>=12: raise
                time.sleep(min(self.poll*2,3)); continue
            if item:
                st=item.get('status',{})
                if st.get('status_str')=='error': raise RuntimeError(str(st))
                if st.get('completed') or item.get('outputs'): return item
            if stop_event is not None and stop_event.wait(self.poll): raise InterruptedError('Generation stopped by user')
            if stop_event is None: time.sleep(self.poll)
        raise TimeoutError('ComfyUI generation timeout')
    def interrupt(self):
        try: requests.post(self.base+'/interrupt',timeout=10)
        except Exception: pass
    def output_files(self,item):
        out=[]
        for node in item.get('outputs',{}).values():
            for key in ('images','gifs'):
                for x in node.get(key,[]):
                    if 'filename' in x:
                        p=Path(x['filename'])
                        if p.is_absolute() and p.is_file():
                            out.append(str(p)); continue
                        if self.output_directory:
                            candidate=Path(self.output_directory)/x.get('subfolder','')/x['filename']
                            if candidate.is_file():
                                out.append(str(candidate)); continue
                        # ComfyUI may run in a separate environment, so retrieve the
                        # image through its supported /view endpoint for GUI/Telegram.
                        try:
                            response=requests.get(self.base+'/view',params={'filename':x['filename'],'subfolder':x.get('subfolder',''),'type':x.get('type','output')},timeout=60)
                            response.raise_for_status()
                            target_dir=self.root/'generated'; target_dir.mkdir(parents=True,exist_ok=True)
                            target=target_dir/Path(x['filename']).name
                            target.write_bytes(response.content)
                            out.append(str(target))
                        except Exception:
                            # Preserve the ComfyUI reference so callers can still report it.
                            out.append(str(p))
        return out
