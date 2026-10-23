"""Map semantic concept spans onto measured narration word boundaries."""
import json
import re
from pathlib import Path
from difflib import SequenceMatcher

def tokens(text):
    return re.findall(r"[^\W_]+(?:['’][^\W_]+)*",text.lower(),re.UNICODE)

def concept_timeline(script, project, durations):
    path=Path(project)/'.stickman/words.json'
    measured=json.loads(path.read_text(encoding="utf-8"))['scenes']
    result={}
    for scene in script['scenes']:
        sid=scene['id']; words=measured[sid]['words']; narration=tokens(scene['voiceover'])
        actual=[]; times=[]
        for w in words:
            for token in tokens(w['w']):
                actual.append(token);times.append(float(w['t']))
        matcher=SequenceMatcher(None,narration,actual,autojunk=False)
        mapping={a+k:b+k for a,b,n in matcher.get_matching_blocks() for k in range(n)}
        if not narration or len(mapping)/len(narration)<0.8:
            raise ValueError(f'{sid}: less than 80% of narration aligns; inspect voice timing or use whisper-local.')
        offsets=[];cursor=0
        for c in scene['concepts']:
            offsets.append(cursor);cursor+=len(tokens(c['narration_span']))
        starts=[0.0]
        for offset in offsets[1:]:
            if offset not in mapping:
                near=next((i for i in range(offset,min(offset+4,len(narration))) if i in mapping),None)
                if near is None: raise ValueError(f'{sid}: concept boundary could not be aligned.')
                offset=near
            starts.append(times[mapping[offset]])
        ends=starts[1:]+[float(durations[sid])]
        if any(b<=a for a,b in zip(starts,ends)): raise ValueError(f'{sid}: invalid concept timing.')
        result[sid]=[{'id':c['id'],'start':a,'end':b} for c,a,b in zip(scene['concepts'],starts,ends)]
    (Path(project)/'.stickman/concepts.json').write_text(json.dumps(result,indent=2), encoding="utf-8")
    return result
