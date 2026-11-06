# Supply changes, driver trajectories and aisle traffic

Current built-in environments use explicit walking graphs. New walking intervals record network movement and waits; earlier straight-line descriptions below document archived replay behavior. Walmart routes use OSM obstacles with estimated internal shared parking surfaces, downtown combines mapped and estimated pedestrian links, and the fictional transfer uses generated paths. No missing network connection falls back to a straight line. All route geometry still requires site review.

## User workflow

1. Choose **Initial supply**: occupancy percentage, an exact empty-space count, or occupied spaces selected on the map. A count of 0 makes the usable inventory full. A count of 5 samples five open spaces using the scenario seed.
2. To choose their locations, set **Map click action** to **Toggle initial occupied space** and click each usable bay. Clicking again removes it. Map selection starts at 0% occupancy. Only clicked spaces start occupied by background vehicles; every other usable space starts empty. Clicking a selected space again clears it.
3. **Toggle initial closure** marks spaces for closure in the next simulation. Closures are separate from occupancy; an unselected closed space stays empty. Original unavailable records cannot be reopened as usable parking.
4. Enable **Model vehicle following and junction queues** for traffic experiments. Leave it disabled to retain the original publication movement model.
5. Start live execution. Set the map action back to **Inspect driver / space**. Inspect a space, then close it, reopen it, or release its background vehicle. Actions apply at the current engine time, which may be ahead of the displayed replay time. The view jumps to that time and the action is recorded.
6. Alternatively, inspect a space and add a timestamped action to the schedule before starting. The same schedule applies to every arm of a matched comparison.
7. Inspect a vehicle to show its traveled route, speed, same-lane neighbors, bumper gap, traffic delay and slowing cause. The last decision scan records visible spaces and feasible candidates. Space-level information can supply remote candidates; these are distinct from local visibility.
8. The traffic panel lists congestion episodes and their causes. Aisle lines show cumulative traffic delay when the overlay is enabled. Download the run before closing the tab.

## Occupancy and closures

The usable physical inventory remains 1,106 spaces. Occupancy is the number of vehicles occupying that inventory divided by 1,106. Closed spaces do not disappear from the denominator, and a vehicle in a closed bay remains counted. The panel separately reports empty-and-open spaces, total closed spaces and closed-but-occupied spaces. Reopening a bay does not remove a vehicle. Manual departures are limited to initial background occupancy; simulated drivers retain their trip lifecycle. Background occupancy is a stock of parked vehicles, not individually tracked agents. Releasing it frees the bay immediately without generating an outbound vehicle trajectory. Generated drivers, including those who abandon, drive along the modeled exit route.

In exact-count mode, the requested number is selected from nonclosed usable spaces; excessive requests are rejected. In map-selection mode, the selected IDs define the exact occupied set, and an empty selection means 0% occupancy. The occupancy slider is used only in percentage mode. All restrictions still apply to driver choice.

## Traffic mechanics and limits

The optional model uses the existing inferred aisle graph and driver decision mechanisms. It limits distance traveled at each physical tick according to a 4.5-m vehicle length and a 2-m minimum following gap. Opposing directions use separate logical lanes. A 1.2-m right-hand display offset makes these directions visible; longitudinal positions and route distances remain on the graph centerline.

Following and downstream capacity are evaluated before crossing priority. Nearby crossing conflicts share one priority order, so closely spaced junctions cannot issue circular yield instructions. The selected vehicle keeps priority while clearing the conflict group; waiting age and stable identifiers resolve new requests. A blocked vehicle cannot reserve a junction it cannot enter. Small road bends and opposing lanes are not treated as crossing traffic. Movement stops at changes in route direction for reassessment. The final parking maneuver can temporarily obstruct the adjacent aisle. An approach delayed by traffic must actually finish before maneuvering and claiming. Drivers whose search deadline expires travel toward their exit before becoming terminal abandoned drivers.

Entry clearance can delay admission to the modeled network. Search duration starts upon admission, so it excludes time waiting outside the entry. These delays must not be interpreted as shorter total arrival-to-parking journeys. Traffic delay counts lost travel time caused by following, junction yielding or parking obstruction; it excludes evaluation stops and the driver's own parking maneuver.

A queue contains vehicles moving below 0.5 m/s because of a modeled traffic constraint. An episode requires at least five consecutive seconds with such a queue in an aisle. Episode records contain start, end, duration, peak count and cause counts measured in constrained vehicle-ticks. The heatmap aggregates traffic delay, not calibrated congestion probabilities. The `cross_aisle` category covers road positions more than 8 m from an inferred longitudinal aisle.

The model has no calibrated acceleration, turning radii, vehicle-specific dimensions, occlusion, pedestrian conflicts or observed junction priorities. It does not prove collision-free vehicle-body motion. Episode thresholds and following parameters are explicit modeling assumptions. Closed parking spaces do not close the driving aisle. Blocking or reconfiguring road access would require a separate topology intervention.

Parking choice retains the original free-flow approach-time estimates. Realized traffic delay contributes to elapsed search, but drivers do not predict future queues when scoring a target. Following reacts to the vehicle ahead; displaying a vehicle behind does not imply a strategic response to it.

## Reproducibility

Supply settings, scheduled and applied actions, source hashes, tracks and traffic telemetry are included in downloads. Tracks store vehicle positions and driver states. Walking is displayed separately from model timestamps as straight-line paths to the assigned door and back; these are derived display trajectories, not observed pedestrian tracks or a sidewalk network. Driver observations are recorded at decision scans, not claimed to be continuously refreshed. A live intervention response supplies updated settings containing applied actions and remaining scheduled events, allowing the sequence to be repeated. Actions at the same timestamp retain their recorded order.

Native and browser execution both use `panda_abm/core/traffic.py`, `panda_abm/core/interventions.py` and the existing decision code. Traffic is opt-in; historical results and performance records must not be presented as validation of this extension. The public website changes only after a refreshed source bundle and release are pushed to GitHub and deployed.

## Simulation duration and pause

Select **10 minutes**, **20 minutes**, **30 minutes**, **1 hour**, or a custom duration from 1 to 360 minutes before starting. **Until all drivers finish** keeps the original full-trip behavior. Duration is simulated time, independent of playback speed. The population size and arrival interval still determine demand; a longer window does not automatically generate more drivers.

Use **Pause simulation** to stop live execution after the current one-second physical step. **Resume simulation** continues the same model, including its random state and occupancy. The playback button also pauses saved replay; computing a complete saved replay is a separate background operation.

A selected duration ends observation without forcing remaining drivers to abandon. Cutoff results distinguish parked drivers, actual abandonments, unfinished searches, and drivers not yet scheduled to arrive. Arrivals scheduled strictly before the cutoff form the evaluation cohort, including those waiting for entry. Mean observed search includes elapsed unfinished searches and is zero before entry; traffic entry waiting is reported separately. These cutoff metrics are not interchangeable with completed-trip results. A driver's existing 600-second search budget remains unchanged. Longer windows preserve decisions before an earlier cutoff and allow later departures and scheduled supply actions to occur.


## Route-following animation and congestion export

New live and recorded simulations retain the actual within-tick route vertices in sample field 6 (after time, x, y, state, chosen space and search duration). The display interpolates along these legs rather than drawing a chord across a bend. This records existing motion; it does not change decision rules, travel speed or claim timing. Older archives have no intermediate vertices: interpolation is allowed only when both positions lie on one graph edge; a turn without vertices uses the saved positions without inventing a diagonal shortcut.

Traffic-enabled scenes show the two directional display lanes at the same 1.2-m offsets used for vehicle placement. Parking approaches remain on their single spur lines, and parked vehicles occupy their configured bay centres. Car headings follow the current motion segment. Route lines are inferred/model-defined geometry, not surveyed lane boundaries or a vehicle-body collision guarantee.

The traffic checkbox is enabled initially for **new interactive scenarios**. Python defaults and archived research simulations remain unchanged. The saved reference replay does not contain traffic interactions; start a new simulation to inspect queues. Uncheck traffic interactions to reproduce the independent-movement mode.

The congestion panel reports sustained jams separately from individual delays. A sustained jam requires at least two traffic-constrained vehicles below 0.5 m/s in the same aisle continuously for at least five simulated seconds. `jam_episodes` records these jams; the backward-compatible `episodes` field records delays involving one or more vehicles. Start, end, duration and peak queued count are recorded. An ongoing jam has no end timestamp, so its observed duration is a lower bound. Aisle aggregation can combine separated queues in the same aisle.

Cause labels describe the modeled constraint: following another vehicle, yielding at a junction, insufficient downstream space, or a parking maneuver obstructing the aisle. `cause_active_seconds` counts simulated seconds with at least one queued vehicle experiencing that cause. Causes can overlap, so these values need not sum to episode duration. `cause_vehicle_seconds` totals queued vehicle-time by cause. `queued_vehicle_delay_s` measures lost free-flow travel time among queued vehicles, not clock duration. Existing `causes` counts remain vehicle-ticks for backward compatibility; integration resolution is recorded separately.

**Download congestion CSV** exports sustained jam episodes (with a minimum-queued-vehicles column) observed by the current displayed time, including cause-active seconds, peak count, ongoing status through a blank end timestamp, and queued vehicle delay. The full JSON download retains per-driver observations, blockers and traffic records. These are model-generated congestion measurements, not calibrated forecasts of actual site traffic.

Checks: `python -m pytest tests/test_route_motion.py tests/test_supply_traffic.py` and `node tests/test_route_motion.cjs`.


## Walking drivers

Each simulated driver has a separate articulated pedestrian display. It appears at the parked vehicle, travels toward the assigned door, disappears during the activity, and returns to the vehicle before departure. The car remains at its bay throughout the walk and activity. **Show walking drivers** toggles visibility, and **Follow selected driver** tracks the pedestrian while visible. One pedestrian represents the driver; passengers are not additional simulated agents.

New recordings and live frames expose `walking_intervals` with phase, start/end timestamps, local-metre endpoints, door ID and space ID. Intervals come from the existing parking, destination-ready and return-ready times. Neither vehicle coordinates nor model decisions, walking duration, activity duration or occupancy rules are changed. The display moves along the current model's straight-line walking distance at its walking speed. It does not add sidewalks, obstacle avoidance, crosswalk delays, door-opening mechanics or interactions with traffic.

Older replays lack those intervals. Their pedestrian display is reconstructed from recorded walking-state transitions, so its timing has the original sampling resolution. It does not recompute or modify historical outcomes. Limb poses and positions follow simulated time, so pausing or seeking does not leave a separately running animation.

Urban controls additionally support assumed fixed-cycle signals, stop dwell, directed roads and through traffic. Signal/stop delay causes are exported alongside following and parking obstructions. See ENVIRONMENTS.md for the assumptions and separate through-vehicle denominators.

Network-enabled downtown pedestrians wait for crossing gaps; vehicles yield to occupied crossings and pedestrian positions. `pedestrian_crossing` appears as a delay cause. Saved walking intervals include the actual route and waits. Old straight-line display metadata remains supported for archived runs.

## Named traffic locations

Downtown reports show street names and block limits from `aisle_network.segment_labels`. For example, `street_2_1` means South 3rd Street between East Grand Avenue and East Garfield Street; `cross_0_1` means East Ivinson Avenue between South 2nd Street and South 3rd Street. Click a location in the congestion panel to highlight its full segment and move the camera there. Comparisons show the same labels. Saved/live/summary records include the label dictionary; CSV exports include road name, block endpoints, full label and original ID. Older downtown recordings can resolve their original fixed-grid IDs. Unassigned connecting-road IDs remain explicitly unassigned. Naming changes do not change traffic calculations.

## Walmart parking modules

Map letters identify the configured parking modules (A–Q in the original estimate; only existing groups in the satellite alternative). Module markers and the Parking modules list are clickable and frame the selected group. Show parking module labels toggles the markers. The list distinguishes usable spaces from total configured records. Slot inspection includes the module name. Driving aisles are separate objects; traffic reports and CSV label each aisle and list the modules it serves. These annotations do not change geometry, capacity or simulation decisions.
