"""Street identities persist independently of UI labels."""
from copy import deepcopy
import pytest
from panda_abm.twin.environments import example_environment,validate_environment,downtown_environment
from panda_abm.twin.replay import record_run,LiveSimulation
from panda_abm.twin.platform import simulate

def test_downtown_block_labels_cover_network():
    e=downtown_environment();n=e['config']['aisle_network'];labels=n['segment_labels']
    assert set(labels)==set(n['aisles'])
    assert labels['street_2_1']['road_name']=='South 3rd Street'
    assert labels['street_2_1']['from']=='East Grand Avenue'
    assert labels['street_2_1']['to']=='East Garfield Street'

def test_saved_live_and_summary_preserve_labels():
    e=example_environment();aid=next(iter(e['config']['aisle_network']['aisles']))
    labels={aid:dict(road_name='Test road',label='Test road — north block')};e['config']['aisle_network']['segment_labels']=labels;e=validate_environment(e)
    settings=dict(environment=e,population_size=1,simulation_duration_s=60)
    assert record_run(settings)['segment_labels']==labels
    assert LiveSimulation(settings).describe()['segment_labels']==labels
    assert simulate(settings)['segment_labels']==labels

def test_invalid_label_id_rejected():
    e=example_environment();e['config']['aisle_network']['segment_labels']={'missing':dict(label='Not a road')}
    with pytest.raises(ValueError,match='labels'):validate_environment(e)


def test_walmart_aisles_list_the_modules_they_serve():
    from panda_abm.environment import load_facility_from_lot_config
    from panda_abm.environment.navigation import AisleNetwork
    from panda_abm.twin.environments import traffic_segment_labels,ROOT
    f=load_facility_from_lot_config(ROOT/'data/lot_config.json');n=AisleNetwork(f);labels=traffic_segment_labels(f,n)
    assert set(labels)==set(n.aisle_nodes)
    for aid,meta in labels.items():
        expected=sorted({f.space_by_id[sid].module_id.replace('Parking_Module_','Module ') for sid in n.aisle_spaces[aid]})
        assert meta['modules']==', '.join(expected)
        assert meta['label'].startswith('Parking aisle ')
