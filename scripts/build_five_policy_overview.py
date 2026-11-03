"""Present all five comparison policies from saved means; no simulations."""
from pathlib import Path
import hashlib
import json
import shutil
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'paper/results_section'
SOURCE = ROOT/'paper/tables/complete/robustness_benchmark_cells.csv'
data = pd.read_csv(SOURCE)
models = ['deterministic', 'rum', 'cpt', 'linear_cpt', 'simple']
names = ['M0: deterministic', 'M1: stochastic', 'CPT', 'Linear CPT', 'Simple search']
plt.rcParams.update({'font.size':13, 'font.weight':'bold', 'axes.labelweight':'bold',
    'axes.labelsize':14, 'xtick.labelsize':12, 'ytick.labelsize':12,
    'axes.spines.top':False, 'axes.spines.right':False, 'pdf.fonttype':42})

def cell(occ, model, info):
    rows = data[np.isclose(data.occupancy, occ) & data.model.eq(model) & data.information.eq(info)]
    assert len(rows) == 1, (occ, model, info, len(rows))
    return rows.iloc[0]

fig, axs = plt.subplots(2, 3, figsize=(12.2, 6.3), layout='constrained', sharey=True)
info_styles = [('unaided', 'Unaided', '#617080', 'o'),
               ('aisle', 'Aisle information', '#c46b00', 's'),
               ('space', 'Space information', '#0072b2', '^')]
metrics = [('mean_search_s','Search duration (s)',1),
           ('mean_walk_parked_m','Walking distance (m)',1),
           ('success','Parking success (%)',100)]
for row, occ in enumerate([.8, .95]):
    for col, (metric, label, scale) in enumerate(metrics):
        ax = axs[row, col]
        for j, (info, name, color, marker) in enumerate(info_styles):
            vals = [cell(occ, model, info)[metric]*scale for model in models]
            ax.scatter(vals, np.arange(5)+(j-1)*.18, label=name, c=color,
                       marker=marker, s=43, edgecolors='white', linewidths=.5, zorder=3)
        ax.set_yticks(range(5), names)
        ax.set_ylim(4.6, -.6)
        ax.set_xlabel(f'({chr(97+row*3+col)}) {label}')
        ax.grid(axis='x', alpha=.18)
        if col == 0: ax.set_ylabel(f'{occ:.0%} initial occupancy')
        if metric == 'success':
            ax.set_xlim((99.4,100.6) if occ == .8 else (76,82))
            ax.set_xticks([99.5,100,100.5] if occ == .8 else [76,78,80,82])
handles, labels = axs[0,0].get_legend_handles_labels()
fig.legend(handles, labels, loc='outside lower center', ncol=3, frameon=False, fontsize=12)
assert all(not ax.get_title() for ax in axs.flat)
for ext in ['png','pdf']:
    fig.savefig(OUT/'figures'/f'five_policy_overview.{ext}', dpi=350, bbox_inches='tight')
plt.close(fig)

rows=[]
for occ in [.4,.8,.95]:
    for model,name in zip(models, ['Deterministic','Stochastic','CPT','Linear CPT','Simple search']):
        if occ == .4 and model == 'linear_cpt':
            rows.append(r'40\% & Linear CPT & --- & --- & --- & --- & --- \\')
            continue
        r=cell(occ,model,'space')
        rows.append(f'{occ:.0%}'.replace('%',r'\%')+' & '+name+' & '+
            ' & '.join(f'{v:.2f}' for v in [r.mean_search_s,r.mean_walk_parked_m,
            r.mean_exit_parked_m,100*r.success])+f' & {r.claims_per_arrival:.3f}'+r' \\')
    if occ != .95: rows.append(r'\midrule')
(OUT/'tables/five_policy_rows.tex').write_text('\n'.join(rows)+'\n',encoding='utf-8')
shutil.copy2(SOURCE,OUT/'source_tables'/SOURCE.name)
audit={'source':str(SOURCE.relative_to(ROOT)),
       'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
       'coverage':'Table includes 40%, 80% and 95% with space information: 14 observed rows and one untested linear-CPT row at 40%. Original wide plot covers 80% and 95%, three information conditions, 30 matched seeds.',
       'interpretation':'Descriptive seed means, not new inferential contrasts. Walking/exit distances condition on parking separately in each arm.',
       'checked_cells':30, 'table_observed_rows':14, 'table_untested_rows':1, 'new_simulations':0}
(OUT/'five_policy_comparison_provenance.json').write_text(json.dumps(audit,indent=2)+'\n')
manifest_path=OUT/'asset_provenance.json'
if manifest_path.exists():
    manifest=json.loads(manifest_path.read_text())
    manifest['main_figures']=5
    manifest['map_figures']=1
    manifest['map_placement']='Experimental Design / Case study and baseline configuration'
    manifest['source_sha256'][str(SOURCE.relative_to(ROOT))]=audit['source_sha256']
    manifest['output_sha256'].update({str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [* (OUT/'figures').glob('five_policy_overview.*'),OUT/'tables/five_policy_rows.tex']})
    manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
print('Five-policy overview: 30 verified mean cells; table covers three occupancy levels with 14 observed rows and one untested row.')
