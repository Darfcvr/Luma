from pathlib import Path
from .utils import load_json,save_json,now
class State:
    def __init__(self,path='state.json'):
        self.path=Path(path); self.data=load_json(self.path,{"generation_count":0,"history":[],"last_prompt":"","last_image":"","last_job_id":"","last_preset":""})
    @property
    def history(self): return self.data.setdefault('history',[])
    def next_generation(self): self.data['generation_count']=int(self.data.get('generation_count',0))+1; return self.data['generation_count']
    def add(self,prompt,job_id='',preset='',image=''):
        self.history.append({'generation':self.data.get('generation_count',0),'job_id':job_id,'preset':preset,'time':now(),'prompt':prompt})
        self.data['history']=self.history[-200:]; self.data['last_prompt']=prompt; self.data['last_job_id']=job_id; self.data['last_preset']=preset
        if image: self.data['last_image']=image
        save_json(self.path,self.data)
    def recent_prompts(self,n=40): return [x.get('prompt','') for x in self.history[-n:]]
