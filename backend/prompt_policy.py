"""One H3 prompt policy shared with the editor's automatic-prompt endpoint."""
import json,re
from pathlib import Path

POLICY=json.loads((Path(__file__).resolve().parents[1]/'lib/h3-prompt-policy.json').read_text())
H3_POLICY='\n'.join(rule.replace('{picture}','<Picture N>').replace('{video}','<Video 1>') for rule in POLICY['rules'])

def validate_h3_prompt(text,mode):
    trigger='motion_transfer:' if mode=='motion' else 'body_swap:'
    if not text.startswith(trigger):raise ValueError(f'Enhanced prompt must start with {trigger}')
    matches=list(re.finditer(r'\b(subject_definitions|summary|retention_analysis|detailed_description|overall_soundscape|non_diegetic_music):',text))
    if [m.group(1) for m in matches]!=POLICY['sections']:raise ValueError('Enhanced prompt must contain all six H3 sections in order')
    for i,match in enumerate(matches):
        end=matches[i+1].start() if i+1<len(matches) else len(text)
        if not text[match.end():end].strip():raise ValueError('Enhanced H3 sections must not be empty')
