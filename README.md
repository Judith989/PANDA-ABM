# PANDA-ABM Research Simulation
Author: Judith Njoku-Vowels


This repository contains the research implementation of PANDA-ABM, a parking agent-based simulation built with Python and Mesa. 
The first version starts with a small synthetic parking environment so the model logic can be tested clearly before moving to the full Walmart/PANDA parking lot and later Cesium integration.


## Step 1: Build The Core Simulation Objects

These first files define the basic objects used by the simulation.

1. Define driver and parking-space state labels  
   `panda_abm/core/states.py`

2. Define parking-space data and parking-space state objects  
   `panda_abm/environment/parking_space.py`

3. Generate the first synthetic parking environment  
   `panda_abm/environment/facility.py`

At this stage, the synthetic environment is intentionally small. 
It is used to test the simulation logic before loading the larger Walmart/PANDA lot with about 1315 parking spaces.



## Verify Step 1

Run:

```powershell
python -m pytest tests -q
```

This basicalyy checks that the basic domain objects are working.


## Step 2: Add Driver Parameters, Population Setup, And Real Lot Input

This step defines who the drivers are, how their behavior is parameterized, and how the project begins connecting to the real Walmart/PANDA parking lot data.

4. Define behavioral parameters that hold the utility weights  
   `panda_abm/behavior/parameters.py`

   These weights describe what the driver cares about when evaluating parking spaces, such as walking distance, price, search time, rule risk, availability, and familiarity.

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

   This file contains the real parking-space layout and markings for the Walmart/PANDA case study. It allows the project to move beyond the small synthetic lot when needed.

At this stage, the model has both:

- a small synthetic facility for quick testing
- a real lot configuration input for the Walmart/PANDA case study

## Verify Step 2

Run:

```powershell
python -m pytest tests -q
```

## Current Test File

The current test file is:

`tests/test_stage_a_domain.py`

This test file checks the foundation of the model before the full agent simulation is added.

It tests that:

1. The behavior parameter objects can be created.

2. The driver attribute and population objects can be created.

3. The synthetic parking facility can be generated.

4. The synthetic facility contains parking spaces, entry points, and exit points.

5. Parking-space states can be initialized correctly.

6. The real Walmart/PANDA lot configuration can be loaded from:

   `data/lot_config.json`

7. The loaded lot config produces a valid facility object with real parking spaces.

At this point, this test does not test driver movement, parking search, utility choice, event logging, or metrics yet. Those will come in later stages.

## Step 3: Add Driver Perception And Choice Set Logic

This step connects the driver behavior setup to the parking environment.

9. Define driver perception  
   `panda_abm/environment/perception.py`

   This file determines which parking spaces a driver can see within a search radius. It also records whether each observed space is truly occupied and whether it appears available to the driver.

10. Define the driver choice set  
   `panda_abm/environment/choice_set.py`

   This file filters the visible parking spaces into the spaces the driver is actually allowed to consider. The filters include availability, accessibility eligibility, reserved-space permits, vehicle compatibility, and walking-distance limits.

After this step, the model can separate:

- spaces that exist in the facility
- spaces the driver can see
- spaces the driver is allowed to choose from

## Verify Step 3

Run:

```powershell
python -m pytest tests -q

```

## Step 4: Add Event Logging, Resource Control, Forecasting Hooks, And The Mesa Simulation Model

This step turns the domain, perception, and decision logic into a working simulation. At this point, the project moves from separate building blocks into a model that can run driver agents through a parking search process.

11. Define the event logger  
   `panda_abm/core/events.py`

   This file records what happens during the simulation. It logs events such as driver arrivals, search starts, candidate observations, candidate evaluations, target selections, parking attempts, successful parking, abandoned searches, and system snapshots.

12. Define the parking resource manager  
   `panda_abm/core/resource_manager.py`

   This file controls parking-space claims and releases. It keeps the rule that one parking space can only be occupied by one vehicle at a time.

13. Define forecasting hooks  
   `panda_abm/forecasting/base.py`  
   `panda_abm/forecasting/null.py`  
   `panda_abm/forecasting/perfect.py`  
   `panda_abm/forecasting/noisy.py`

   These files create a clean place for future prediction logic. The current version can run with no forecast, a perfect forecast control condition, or a noisy forecast condition. This does not train an AI model yet. It only prepares the simulation for later digital-twin prediction work.

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

   This file creates standard figures for search time, walking distance, chosen spaces, and occupancy over time.

18. Define JSON exports for digital-twin use  
   `panda_abm/export/json_exporter.py`

   This file exports event streams, vehicle trajectories, and simulation state snapshots as JSON.

19. Define the digital-twin state snapshot  
   `panda_abm/twin/state.py`

   This file creates a structured state snapshot with vehicles, parking spaces, and system occupancy. This is the part that can later connect to Cesium.

20. Define the experiment runner  
   `panda_abm/simulation/runner.py`

   This file runs the simulation across decision models and repetitions, then saves metrics, plots, event logs, trajectories, and digital-twin JSON outputs.

After this step, the project can run a full simulation experiment instead of only testing individual objects.

The model can now:

- create driver agents
- advance simulation time
- let drivers search for visible and feasible spaces
- evaluate candidate spaces with the selected decision model
- claim and release parking spaces safely
- record events during the run
- derive metrics from the event log
- export CSV, plots, and JSON files for later Cesium integration

## Verify Step 4

Run:

```powershell
python -m pytest tests -q
```

## Step 5: Run Demo Experiments And Generate Outputs

At this stage, the main simulation code is in place and the test suite passes. The next step is to run the model and generate research outputs.

The experiment runner compares the three decision-model levels:

- `M0 deterministic`: chooses the highest-utility feasible space
- `M1 random utility`: uses softmax choice, so the driver usually prefers better spaces but can still vary
- `M2 CPT`: adds reference-dependent valuation for walking distance and search time

The current behavior profile is still focused on the first persona:

- `convenience_seeker`

This is intentional. The first full experiment checks that one driver behavior profile works end to end before adding more personas.

## Run A Small Demo

Run:

```powershell
python scripts\run_demo.py --output results\demo_research
```

The demo is a quick pipeline check. It confirms that the simulation runs, metrics are produced, plots are created, and JSON exports are written.

## Run A Larger Baseline Experiment

Run:

```powershell
python scripts\run_experiment.py --repetitions 10 --population-size 48 --initial-occupancy-rate 0.35 --output results\baseline
```

The larger run gives a better baseline than the small demo because it uses more drivers and more repetitions.

## Output Files

After a run, check the output folder:

```text
results/
  raw/
    events/events.csv
    agents/agent_metrics.csv
    system/system_metrics.csv
    decision_log.csv
    trajectories/trajectories.csv
  tables/
    model_comparison.csv
  figures/
    search_time_distribution.png
    walking_distance_boxplot.png
    chosen_space_distribution.png
    occupancy_over_time.png
  twin_exports/
    vehicle trajectory JSON, one file per run
  event_exports/
    raw event stream JSON, one file per run
  state_exports/
    final digital-twin state JSON, one file per run
```

Start with:

`results/baseline/tables/model_comparison.csv`

This table reports:

- success rate
- abandonment rate
- mean search time
- median search time
- 90th percentile search time
- mean walking distance
- mean search distance
- mean rejected spaces

## Why The Demo Variants Can Look Similar

The demo is intentionally easy. It uses one main driver persona, a manageable synthetic environment, and a moderate occupancy level. Under those conditions, M0, M1, and M2 can all park most drivers successfully.

That does not mean the decision models are identical. In the demo output, walking distance and search distance can still differ across models. The headline success and abandonment rates may look similar because the scenario does not create enough pressure.

Stronger differences should appear after testing harder scenarios, such as:

- higher initial occupancy
- larger driver populations
- tighter acceptance thresholds
- more unavailable or restricted spaces
- multiple driver personas
- stronger differences in search tolerance and walking tolerance

## Current Test Result

Run:

```powershell
python -m pytest tests -q
```

Current result:

```text
23 passed
```

This confirms that the domain objects, decision models, simulation model, event logging, metrics, plots, exports, and digital-twin state outputs are working.

## Next Development Step

The next model-development step is to add more personas and scenario mixes. The current implementation focuses on `convenience_seeker`. Future behavior profiles can include:

- cost-sensitive driver
- time-sensitive driver
- risk-averse driver
- accessibility-seeking driver

Those profiles will be added by expanding:

- `panda_abm/behavior/parameters.py`
- `panda_abm/behavior/factory.py`

After that, Cesium integration can use the JSON exports already produced by the simulation.
