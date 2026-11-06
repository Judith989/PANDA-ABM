"""Reproducible, timestamped supply changes shared by live and batch execution."""


def apply_intervention(model, event):
    action = event['action']
    ids = event['space_ids']
    # Validate the entire action before modifying any state.
    for sid in ids:
        if sid not in model.space_states:
            raise ValueError(f'Unknown parking space: {sid}')
        if model.facility.space_by_id[sid].unavailable:
            raise ValueError(f'{sid} is outside the usable inventory')
        occupant = model.resource_manager.occupant(sid)
        if action == 'release' and occupant not in (None, 'initial_occupancy'):
            raise ValueError('Only background vehicles can be released manually; simulated drivers complete their trips')
    for sid in ids:
        state = model.space_states[sid]
        if action == 'close':
            state.unavailable = True
        elif action == 'open':
            state.unavailable = False
        elif action == 'release' and state.occupied:
            model.resource_manager.release_space('initial_occupancy', sid)
        model.event_logger.log('SupplyIntervention', model.clock_s, space_id=sid,
                               details={'action': action})
    record = dict(time_s=model.clock_s, action=action, space_ids=list(ids))
    model.intervention_log.append(record)
    return record


def supply_snapshot(model):
    states = list(model.space_states.values())
    spaces = model.facility.space_by_id
    usable = [s for s in states if not spaces[s.space_id].unavailable]
    occupied = sum(s.occupied for s in usable)
    return dict(usable_inventory=len(usable), occupied=occupied,
                free=sum(not s.occupied and not s.unavailable for s in usable),
                closed=sum(s.unavailable for s in usable),
                closed_occupied=sum(s.unavailable and s.occupied for s in usable),
                occupancy_pct=100*occupied/len(usable) if usable else 0.,
                closed_space_ids=sorted(s.space_id for s in usable if s.unavailable))
