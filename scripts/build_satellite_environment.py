"""Derive an opt-in simulation config; never replace the original Walmart config."""
from pathlib import Path
from copy import deepcopy
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]

def main():
    original_path=ROOT/'data/lot_config.json'
    proposal_path=ROOT/'research/alignment_review/20261105/lot_config.candidate.json'
    before=original_path.read_bytes();old=json.loads(before);proposal=json.loads(proposal_path.read_text(encoding='utf8'))
    assert proposal['meta']['original_config_sha256']==hashlib.sha256(before).hexdigest()
    lookup={s['id']:s for s in old['slots']};result=deepcopy(proposal)
    for s in result['slots']:
        source=lookup[s['nearest_original_id']]
        for key in ('type','is_accessible','is_reserved','is_unavailable','is_blocked','price_per_hour'):
            if key in source:s[key]=source[key]
        s['restriction_review_status']='assumed_from_nearest_original_record_not_field_verified'
    meta=result['meta'];meta.update(lot_name='Walmart satellite-estimated layout',simulation_ready=True,alignment_status='provisional_satellite_simulation_variant',restriction_assumption='Each proposed bay inherits type/accessibility/reservation/unavailable/blocked/price fields from its nearest original record. This is not observed or calibrated classification.',source_candidate_sha256=hashlib.sha256(proposal_path.read_bytes()).hexdigest(),note='Separate opt-in simulation geometry. 472 provisional row-fitted records; not a surveyed or independently counted inventory. Original Walmart geometry and paper results remain unchanged.')
    meta['accessible_slot_ids']=[s['id'] for s in result['slots'] if s.get('is_accessible')]
    meta['accessible_slots']=len(meta['accessible_slot_ids'])
    meta['usable_slots']=sum(not(s.get('is_unavailable') or s.get('is_blocked')) for s in result['slots'])
    meta['geometry_provenance']['restrictions']=meta['restriction_assumption']
    (ROOT/'data/lot_config.satellite_estimated.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    assert original_path.read_bytes()==before
    print(json.dumps(dict(records=len(result['slots']),usable=meta['usable_slots'],accessible=meta['accessible_slots'],original_unchanged=True)))

if __name__=='__main__':main()
