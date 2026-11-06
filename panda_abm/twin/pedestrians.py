"""Walking display intervals derived from the existing driver lifecycle timestamps."""
def walking_intervals(agent, speed_m_s, space_by_id=None):
    if getattr(agent,'walking_route_data',None) is not None:return list(getattr(agent,'pedestrian_segments',[]))
    if agent.parking_time_s is None or agent.walking_distance_m is None:return []
    space=(space_by_id if space_by_id is not None else agent.model.facility.space_by_id)[agent.chosen_space_id]
    bay=[space.x_m,space.y_m];door=list(agent.attributes.destination)
    duration=agent.walking_distance_m/speed_m_s
    result=[dict(phase='to_door',start_s=agent.parking_time_s,end_s=agent.destination_ready_s,from_m=bay,to_m=door,door=agent.attributes.walmart_door_id,space=agent.chosen_space_id)]
    if hasattr(agent,'return_ready_s'):
        result.append(dict(phase='to_vehicle',start_s=agent.return_ready_s-duration,end_s=agent.return_ready_s,from_m=door,to_m=bay,door=agent.attributes.walmart_door_id,space=agent.chosen_space_id))
    return result
