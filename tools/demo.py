"""Offline integration demo: procedural pictures + local tone, no provider calls."""
import argparse
import json
from pathlib import Path
import subprocess
from PIL import Image,ImageDraw
from stickman.config import default_config
from stickman.align import align_words
from stickman.render.composer import compose
from stickman.verify import verify
from stickman.thumbnailx import make_thumbnail

def demo(root):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    for d in ['voice','stills/work','.stickman']:(root/d).mkdir(parents=True,exist_ok=True)
    scenes=[];meta={}
    for i,action in enumerate(['throws a paper airplane','points at moving air'],1):
        sid=f's0{i}';text=['A paper airplane moves forward and gently glides through the air.','Its wings change the flow of air while gravity pulls it down.'][i-1]
        scenes.append({'id':sid,'voiceover':text,'visual':'stickman '+action,'action':action,'anchor':f'paper plane {i}','concepts':[{'id':f'c0{i}','anchor':f'plane {i}','narration_span':text,'subject':'stickman','visible_action':action,'object':'paper plane','spatial_relation':'right','composition':'wide','semantic_visual':'stickman '+action,'overlay_hint':'AIR IN MOTION' if i==1 else '2 FORCES'}]})
        image=Image.new('RGB',(1280,720),'white');dr=ImageDraw.Draw(image)
        x=300+i*70;dr.ellipse((x-65,160,x+65,290),outline='#1a1a1a',width=8);dr.line((x,290,x,470),fill='#1a1a1a',width=8)
        for a,b in [((x,330),(x+150,300)),((x,350),(x-80,410)),((x,470),(x-80,590)),((x,470),(x+80,590))]:dr.line((*a,*b),fill='#1a1a1a',width=8)
        dr.polygon([(800,240),(1020,280),(840,330),(900,280)],fill='#f2c94c',outline='#1a1a1a')
        image.save(root/f'stills/work/s{i:02d}_c0{i}.png')
        audio=root/f'voice/{sid}.mp3'
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i',f'sine=frequency={200+i*40}:duration=3','-af','volume=0.4','-c:a','libmp3lame',str(audio)],check=True)
        meta[sid]={'duration_s':3.0}
    script={'title':'Paper Airplane Demo','language':'en','target_minutes':0.1,'thumbnail_hook':'WHY IT GLIDES','scenes':scenes}
    (root/'script.json').write_text(json.dumps(script,indent=2), encoding='utf-8');(root/'voice/meta.json').write_text(json.dumps(meta), encoding='utf-8')
    align_words(script,root,mode='proportional',meta=meta)
    master=compose(root,script,{sid:3 for sid in meta},default_config())
    expected=json.loads((root/'.stickman/compose_report.json').read_text(encoding='utf-8'))['expected_duration_s']
    ok,report=verify(master,expected_duration_s=expected)
    # Make portable report for distribution; no absolute workstation paths.
    report['mp4']='output/master.mp4'
    (root/'output/technical-check.json').write_text(json.dumps(report,indent=2), encoding='utf-8')
    make_thumbnail(src=root/'stills/work/s01_c01.png',out=root/'output/thumbnail.png',hook='WHY IT GLIDES')
    print(f'Demo: {master}; technical checks: {ok}')
    if not ok:raise SystemExit(3)
    return master

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',default='demo-local');demo(p.parse_args().out)
