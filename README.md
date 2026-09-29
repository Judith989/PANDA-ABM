# PANDA-ABM Research Simulation

Author: Judith Njoku-Vowels

This repository contains the research implementation of PANDA-ABM, a parking agent-based simulation built with Python and Mesa.

The first version starts with a small synthetic parking environment so the model logic can be tested clearly before moving to the full Walmart/PANDA parking lot and later Cesium integration.

The current codebase supports:

- synthetic parking facility experiments
- Walmart/PANDA real lot experiments using `data/lot_config.json`
- multiple driver personas
- multiple decision models
- event logging
- metrics tables
- plots
- JSON exports for future digital twin and Cesium use

## Step 1: Core States And Parking Spaces

These first files define the basic objects used by the simulation.

1. Define driver and parking-space state labels  
   `panda_abm/core/states.py`

2. Define parking-space data and parking-space state objects  
   `panda_abm/environment/parking_space.py`

3. Generate the first synthetic parking environment  
   `panda_abm/environment/facility.py`

At this stage, the synthetic environment is intentionally small. It is used to test the simulation logic before loading the larger Walmart/PANDA lot with about 1315 parking spaces.

## Step 2: Driver Behavior Parameters And Populations

This step defines who the drivers are, how their behavior is parameterized, and how the project begins connecting to the real Walmart/PANDA parking lot data.

4. Define behavioral parameters that hold utility weights  
   `panda_abm/behavior/parameters.py`

   These weights describe what a driver cares about when evaluating parking spaces, such as walking distance, price, search time, rule risk, availability, familiarity, guidance, and compliance.

5. Define CPT reference points for later M2 behavior  
   `panda_abm/behavior/references.py`

   These reference points help represent how a driver compares an outcome with what they expected, such as expected walking distance or expected search time.

6. Define driver attributes and population data structures  
   `panda_abm/behavior/population.py`

   This file defines each driver's profile, including persona, destination, arrival time, vehicle type, familiarity, accessibility eligibility, permit status, and walking tolerance.

7. Create a reproducible driver population  
   `panda_abm/behavior/factory.py`

   This file creates driver populations using a random seed so that the same drivers can be reused across different model versions.

8. Add the real Walmart/PANDA lot configuration file  
   `data/lot_config.json`

   This file contains the real parking-space layout and markings for the Walmart/PANDA case study.

The model now has both:

- a small synthetic facility for quick testing
- a real lot configuration input for the Walmart/PANDA case study

## Step 3: Perception And Choice Sets

This step connects the driver behavior setup to the parking environment.

9. Define driver perception  
   `panda_abm/environment/perception.py`

   This file determines which parking spaces a driver can see within a search radius. It also records whether each observed space is truly occupied and whether it appears available to the driver.

10. Define the driver choice set  
    `panda_abm/environment/choice_set.py`

    This file filters visible spaces into spaces the driver is actually allowed to consider. The filters include availability, accessibility eligibility, reserved-space permits, vehicle compatibility, and walking-distance limits.

After this step, the model can separate:

- spaces that exist in the facility
- spaces the driver can see
- spaces the driver is allowed to choose from

## Step 4: Decision Models

This step adds the decision logic used when a driver evaluates candidate parking spaces.

The current suite compares three decision-model levels:

- `M0 deterministic`
- `M1 random utility`
- `M2 cumulative prospect theory`

The decision files are stored in:

```text
panda_abm/behavior/decision/
```

The same environment and population can be run through different behavioral assumptions.

### M0 Deterministic Choice

The deterministic model chooses the feasible parking space with the highest utility.

It is useful as a clean baseline because it assumes the driver always picks the best option according to the utility function.

### M1 Random Utility Choice

The random utility model uses a softmax-style choice rule. Better spaces are more likely to be selected, but the driver does not always choose the exact maximum.

This is useful because real drivers do not behave perfectly every time.

### M2 CPT Choice

The CPT model builds from the random utility model but adds reference-dependent behavior.

This allows walking distance and search time to be evaluated relative to what the driver expected. It is useful for representing disappointment, tolerance, and sensitivity to losses.

## Step 5: Simulation, Events, Metrics, And Exports

This step turns the domain, perception, and decision logic into a working simulation.

11. Define the event logger  
    `panda_abm/core/events.py`

    This file records what happens during the simulation. It logs driver arrivals, search starts, candidate observations, candidate evaluations, target selections, parking attempts, successful parking, abandoned searches, and system snapshots.

12. Define the parking resource manager  
    `panda_abm/core/resource_manager.py`

    This file controls parking-space claims and releases. It keeps the rule that one parking space can only be occupied by one vehicle at a time.

13. Define forecasting hooks  
    `panda_abm/forecasting/`

    These files create a place for future prediction logic. The current version can run with no forecast, a perfect forecast control condition, or a noisy forecast condition. This does not train an AI model yet.

14. Define the driver agent  
    `panda_abm/core/agent.py`

    This file defines one driver in the parking simulation. The driver moves through states such as arriving, searching, targeting, parked, walking to the destination, returning to the vehicle, exiting, left, or abandoned.

15. Define the parking model  
    `panda_abm/core/model.py`

    This file defines the Mesa model that holds the facility, driver population, parking-space states, decision model, event logger, resource manager, forecasting hook, and simulation clock.

16. Define metrics from simulation events  
    `panda_abm/metrics/collector.py`

    This file turns the event log into result tables, including agent outcomes, system metrics, decision logs, and trajectories.

17. Define analysis plots  
    `panda_abm/analysis/plots.py`

    This file creates standard figures for search time, walking distance, chosen spaces, occupancy over time, and persona-level comparisons.

18. Define JSON exports for digital-twin use  
    `panda_abm/export/json_exporter.py`

    This file exports event streams, vehicle trajectories, and simulation state snapshots as JSON.

19. Define the digital-twin state snapshot  
    `panda_abm/twin/state.py`

    This file creates a structured state snapshot with vehicles, parking spaces, and system occupancy. This is the part that can later connect to Cesium.

20. Define the experiment runner  
    `panda_abm/simulation/runner.py`

    This file runs the simulation across decision models and repetitions, then saves metrics, plots, event logs, trajectories, and digital-twin JSON outputs.

## Step 6: Demo Experiment

The demo uses the small synthetic facility. This should be run first because it is quick and easier to inspect.

Run:

```powershell
python scripts\run_demo.py --output results\demo_research
```

The demo checks that the full pipeline works:

- simulation runs
- events are recorded
- metrics are produced
- plots are created
- JSON exports are written

## Step 7: Real Lot Baseline Experiment

The real lot baseline uses the Walmart/PANDA parking layout from:

```text
data/lot_config.json
```

Run:

```powershell
python scripts\run_experiment.py --facility-config data\lot_config.json --output results\real_lot_baseline --scenario-id real_lot_baseline --seed 42 --repetitions 10 --population-size 48 --initial-occupancy-rate 0.35
```

This is the main baseline run for the real facility.

## Step 8: Stress Test Experiment

The stress test uses the real lot but creates a harder parking condition by increasing occupancy and demand.

Run:

```powershell
python scripts\run_experiment.py --facility-config data\lot_config.json --output results\stress_test --scenario-id stress_test --seed 42 --repetitions 20 --population-size 80 --initial-occupancy-rate 0.80
```

The stress test is important because the decision models may look similar in easy conditions. Differences should become clearer when the lot is crowded.

## Step 9: Digital Twin And Future Cesium Integration

The current system is a simulation-based digital twin prototype.

Right now, the model does not train an AI model in real time. Instead, it generates simulated current states, event streams, trajectories, and final state snapshots.

These outputs are saved as JSON:

```text
twin_exports/
event_exports/
state_exports/
```

Later, Cesium can read these exports or receive streamed versions of the same state fields.

The important digital twin fields include:

- vehicle ID
- persona
- vehicle state
- x and y position
- chosen parking space
- search time
- candidate parking spaces
- parking-space status
- system occupancy

This keeps Cesium integration possible without forcing the visualization into the first research experiments.

## Output Folder Structure

Each experiment writes outputs like this:

```text
results/
  raw/
    events/
      events.csv
    agents/
      agent_metrics.csv
    system/
      system_metrics.csv
    decision_log.csv
    trajectories/
      trajectories.csv

  tables/
    model_comparison.csv
    persona_comparison.csv
    decision_model_persona_comparison.csv

  figures/
    search_time_distribution.png
    walking_distance_boxplot.png
    chosen_space_distribution.png
    occupancy_over_time.png
    success_rate_by_persona.png
    search_time_by_persona.png
    walking_distance_by_persona.png
    decision_model_by_persona.png

  twin_exports/
    vehicle trajectory JSON, one file per run

  event_exports/
    raw event stream JSON, one file per run

  state_exports/
    final digital-twin state JSON, one file per run
```

## Main Metrics

The standard agent-level metrics include:

- `persona`
- `decision_model`
- `run_id`
- `driver_id`
- `success`
- `abandoned`
- `chosen_space_id`
- `search_time`
- `walking_distance`
- `search_distance`
- `rejected_spaces`
- `final_state`

The summary tables report:

- success rate
- abandonment rate
- mean search time
- median search time
- 90th percentile search time
- mean walking distance
- mean search distance
- mean rejected spaces

## Verify The Code

Run:

```powershell
python -m pytest tests -q
```

A passing test suite means the domain objects, behavior setup, decision models, simulation model, event logging, metrics, plots, exports, and digital-twin state outputs are working.

## Suggested Run Order

Use this order when reproducing the project:

```powershell
python -m pytest tests -q

python scripts\run_demo.py --output results\demo_research

python scripts\run_experiment.py --facility-config data\lot_config.json --output results\real_lot_baseline --scenario-id real_lot_baseline --seed 42 --repetitions 10 --population-size 48 --initial-occupancy-rate 0.35

python scripts\run_experiment.py --facility-config data\lot_config.json --output results\stress_test --scenario-id stress_test --seed 42 --repetitions 20 --population-size 80 --initial-occupancy-rate 0.80
```

## Notes

The small demo is mainly a pipeline check.

The real lot baseline is the main Walmart/PANDA experiment.

The stress test is used to make behavioral differences easier to see.

Cesium integration will come later. The current code already prepares for it through digital-twin JSON exports.
