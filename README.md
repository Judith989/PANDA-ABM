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


## Step 2: Add Driver Parameters And Population Setup

The next files define who the drivers are and how their behavior is parameterized.


Next - add driver parameters

4. Define behavioral parameters that holds utility weights  --  `panda_abm/behavior/parameters.py`
5.  Define CPT reference points for later M2 behavior -- `panda_abm/behavior/references.py`
6. Define driver attributes and population data structures `panda_abm/behavior/population.py`
7.  Create a reproducible driver population `panda_abm/behavior/factory.py`