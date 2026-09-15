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