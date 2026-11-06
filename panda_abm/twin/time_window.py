"""Observation windows; stopping observation does not abandon unfinished drivers."""
from statistics import fmean


def window_status(agent, end_s):
    arrived = bool(agent.arrival_time_s < end_s)
    parked = agent.parking_time_s is not None
    resolved = agent.search_ended_s is not None
    elapsed = (max(0., (agent.search_ended_s if resolved else end_s)-agent.search_started_s)
               if agent.search_started_s is not None else 0.)
    return dict(observed_arrival=arrived, search_s=elapsed,
                search_status=('not_arrived' if not arrived else 'parked' if parked else
                               'abandoned' if resolved else 'unfinished'),
                right_censored=arrived and not resolved,
                state_at_cutoff=agent.state.value,
                success=parked if arrived else None)


def window_summary(model):
    agents = list(model.agents)
    rows = [window_status(a, model.clock_s) for a in agents]
    arrived = [(a, r) for a, r in zip(agents, rows) if r['observed_arrival']]
    parked = [a for a, r in arrived if r['success']]
    spaces = model.facility.space_by_id
    mean = lambda values: fmean(values) if values else None
    result = dict(drivers=len(agents), arrivals=len(arrived),
                parked=len(parked), abandoned=sum(r['search_status']=='abandoned' for _, r in arrived),
                unfinished=sum(r['right_censored'] for _, r in arrived),
                not_arrived=len(agents)-len(arrived),
                awaiting_entry=sum(a.search_started_s is None for a, _ in arrived),
                active_trips=sum(a.state.value not in ('left','abandoned') for a, _ in arrived),
                mean_search_s=mean([r['search_s'] for _, r in arrived]),
                mean_walk_m=mean([a.walking_distance_m for a in parked]),
                mean_exit_m=mean([spaces[a.chosen_space_id].exit_distance(a.attributes.preferred_exit_id) for a in parked]),
                search_measure='Elapsed search observed within the window, including unfinished searches; zero before admission',
                success_measure='Parked by the cutoff among scheduled arrivals before the cutoff',
                window_end_s=model.clock_s)
    if model.traffic:
        entries=[max(0.,(a.search_started_s if a.search_started_s is not None else model.clock_s)-a.arrival_time_s) for a,_ in arrived]
        result.update(mean_entry_delay_s=mean(entries),
                      mean_arrival_to_search_end_s=mean([entry+r['search_s'] for entry,(_,r) in zip(entries,arrived)]))
    return result


def run_window(model, duration_s):
    if duration_s is None:
        model.run_until_complete()
    else:
        while model.clock_s < duration_s:
            model.step()
