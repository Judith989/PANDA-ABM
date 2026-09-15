from panda_abm.behavior import BehavioralParameters, DriverAttributes, DriverSpec, PopulationSpec, ReferencePoints
from panda_abm.core.states import SpaceType, StateProvenance
from panda_abm.environment import ParkingSpace, ParkingSpaceState, generate_synthetic_facility, load_facility_from_lot_config


def test_synthetic_facility_has_expected_small_demo_shape():
    facility = generate_synthetic_facility(seed=42)

    assert facility.synthetic is True
    assert facility.facility_id == "synthetic_demo"
    assert len(facility.spaces) == 36
    assert facility.module_ids == ("A", "B", "C")


def test_parking_space_state_separates_mutable_occupancy_from_geometry():
    space = ParkingSpace(space_id="S001", module_id="A", x_m=0.0, y_m=0.0)
    state = ParkingSpaceState.from_space(space)

    assert space.space_id == state.space_id
    assert state.occupied is False
    state.mark_occupied("D001")
    assert state.occupied is True
    assert state.occupant_id == "D001"
    state.release()
    assert state.occupied is False
    assert state.occupant_id is None


def test_reference_drift_toggle():
    refs = ReferencePoints(r_walk_m=100.0, kappa_walk=0.5, drift_enabled=False)
    refs.update(observed_walk_m=200.0)
    assert refs.r_walk_m == 100.0

    refs.drift_enabled = True
    refs.update(observed_walk_m=200.0)
    assert refs.r_walk_m == 150.0


def test_population_spec_is_frozen_and_reusable():
    attrs = DriverAttributes(driver_id="D001", destination_x_m=10.0, destination_y_m=5.0)
    spec = DriverSpec(attrs, BehavioralParameters(), ReferencePoints())
    population = PopulationSpec(population_id="pop_demo", seed=123, drivers=(spec,))

    assert population.drivers[0].driver_id == "D001"
    assert population.as_dict()["drivers"][0]["attributes"]["vehicle_type"] == "sedan"


def test_real_lot_config_loader_maps_existing_schema():
    facility = load_facility_from_lot_config("data/lot_config.json")

    assert facility.synthetic is False
    assert len(facility.spaces) == 1315
    assert facility.spaces[0].space_id.startswith("P-")
    assert any(space.space_type == SpaceType.ACCESSIBLE for space in facility.spaces)


def test_state_provenance_values_are_distinct():
    assert StateProvenance.OBSERVED_CURRENT != StateProvenance.SIMULATED_CURRENT
