# PANDA-ABM Research Simulation

Author: Judith Njoku-Vowels

Updated: 28 October 2026

PANDA-ABM was developed as a parking agent-based research simulation using Python and Mesa.

This guide describes the model components and provides commands for running synthetic examples, Walmart parking experiments, matched information comparisons, behavioral analysis and model audits.

For the public Cesium website, see the [Vercel deployment guide](web/DEPLOYMENT.md).
The checked-in release snapshot builds without private study archives or a Python server.

The implementation supported:

- synthetic and Walmart/PANDA parking environments
- driver attributes, preferences, constraints and reference points
- deterministic utility, random utility and cumulative prospect theory decisions
- vehicle movement through parking aisles
- unaided, aisle-level and space-level parking information
- event logging, metrics, plots and experiment reports
- a Cesium website for live simulations, saved replays and matched comparisons

## Installation

Run these commands from the repository root in PowerShell:

~~~powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt -r requirements-analysis.txt
~~~

The first requirements file contains the simulation dependencies. The second adds packages used for post-simulation clustering and stability analysis.

The commands below use python from the selected environment. If the environment is not activated, replace python with ./.venv/Scripts/python.exe.

## Step 1: Core States And Parking Spaces

These files established the simulation's physical objects and state labels.

1. [panda_abm/core/states.py](panda_abm/core/states.py)

   This file defined the driver states used throughout a trip and the parking-space types used by the facility. Shared labels allowed the agent, event logger and analysis code to refer to the same states.

1. [panda_abm/environment/parking_space.py](panda_abm/environment/parking_space.py)

   This file defined the parking-space data and its changing occupancy state. It stored space position, type, restrictions and distance information so that feasibility, movement and choice calculations could use the same space records.

1. [panda_abm/environment/facility.py](panda_abm/environment/facility.py)

   This file generated the small synthetic facility and loaded the Walmart lot configuration. It assembled parking spaces and facility landmarks for use by the model.

1. [panda_abm/environment/coordinates.py](panda_abm/environment/coordinates.py)

   This file converted latitude and longitude into local coordinates measured in metres. The local coordinates were used for movement, visibility and distance calculations within the facility.
The synthetic facility was used for small examples and software checks. The Walmart/PANDA environment was loaded from [data/lot_config.json](data/lot_config.json).

The case study represented the Walmart Supercenter parking lot in Laramie, Wyoming. The store lay south of the main parking area. The main area contained long rows of parking spaces separated by driving aisles, and smaller parking groups extended along the sides of the building.

The configuration contained **1,315 estimated slot records across 17 modules (A–Q)**. Modules A–N accounted for 1,245 records, and the side groups O–Q accounted for 70. Of all records, 34 were marked accessible and 209 were marked blocked/unavailable, leaving 1,106 unblocked records before initial occupancy and driver-specific restrictions were applied. These counts described the simulation configuration, rather than a surveyed inventory of usable spaces.

Slot coordinates were aligned to satellite imagery and reviewed visually. The layout and aisle network remained estimates. Four landmarks were included:

- Door 1 and Door 2: the western and eastern doors along the parking-facing store wall.
- Entry/Exit A: the northern driveway. Entry/Exit B: the eastern driveway at Vista Drive. Both were treated as allowing entry and exit.

![Satellite view of Walmart with Door 1, Door 2, Entry/Exit A and Entry/Exit B marked](research/site_assets/walmart_doors_and_access.png)

Door 1 and Door 2 represented the store entrances; A and B represented vehicle entry/exit points. Markers followed the estimated coordinates in the lot configuration. Satellite image: Google Maps, with imagery attribution retained in the figure.

Each slot was assigned separate distances to Door 1, Door 2, Entry/Exit A and Entry/Exit B. These were stored as distance_to_door_1_m, distance_to_door_2_m, distance_to_exit_a_m and distance_to_exit_b_m. They represented straight-line distances; vehicle movement followed the aisle network.

To recalculate the distance fields after editing the landmarks or slot coordinates:

~~~powershell
python scripts/update_lot_distances.py
~~~

## Step 2: Driver Attributes, Preferences And Populations

This step created the drivers who used the facility.

1. [panda_abm/behavior/population.py](panda_abm/behavior/population.py)

   This file defined driver attributes and population specifications. Each specification held the arrival time, destination, vehicle characteristics, familiarity, eligibility, permit status and walking constraints needed to recreate a driver.

1. [panda_abm/behavior/parameters.py](panda_abm/behavior/parameters.py)

   This file held the utility weights, acceptance threshold and response temperature. The weights represented the importance of walking, price, search, rule risk, availability, familiarity, guidance, compliance and exit proximity when evaluating an offer.

1. [panda_abm/behavior/references.py](panda_abm/behavior/references.py)

   This file defined expected walking, search and exit-distance reference points. These expectations provided the comparison levels used when CPT evaluated outcomes as gains or losses.

1. [panda_abm/behavior/cpt_parameters.py](panda_abm/behavior/cpt_parameters.py)

   This file defined CPT value curvature, loss aversion and probability-weighting parameters. It also recorded parameter-source information so that literature benchmarks and simulation assumptions could be distinguished.

1. [panda_abm/behavior/continuous.py](panda_abm/behavior/continuous.py)

   This file sampled continuous driver preferences, attributes and constraints with reproducible random streams. The resulting population could vary in tastes and expectations while preserving the same sampled drivers across matched experiments.

1. [panda_abm/behavior/factory.py](panda_abm/behavior/factory.py)

   This file provided the entry points for creating reproducible populations and controlled comparison populations. It connected population specifications, behavioral parameters and reference points to the driver setup used by the simulation.
A driver's attributes included arrival time, destination, vehicle type, familiarity, eligibility, permit status and walking limits. Preferences determined the importance of walking, price, search, availability, rule risk, exit proximity and other implemented features.

Population specifications can be saved and reused so that different decision models and information conditions receive the same drivers.

## Step 3: Perception, Information And Choice Sets

This step determined what drivers knew and which spaces they could consider.

1. [panda_abm/environment/perception.py](panda_abm/environment/perception.py)

   This file determined which spaces a driver could observe locally and recorded their perceived availability. It also provided individual-space reports for the space-information condition, allowing reported targets beyond local visibility to enter consideration.

1. [panda_abm/environment/information.py](panda_abm/environment/information.py)

   This file calculated compatible free-space counts by aisle and used those counts to guide exploration. It supplied aisle-level information without revealing the identities of distant free spaces to the driver.

1. [panda_abm/environment/choice_set.py](panda_abm/environment/choice_set.py)

   This file filtered observed or reported spaces into the offers a driver could consider. The checks covered perceived availability, vehicle compatibility, accessibility eligibility, reserved-space permission and walking-distance limits.
Three information conditions were implemented:

| Command-line value | Driver information and search behavior |
|---|---|
| unaided | Observe nearby spaces and explore the parking aisles |
| aisle | Receive compatible free-space counts by aisle; use them to guide exploration when local offers are declined |
| space | Receive individual current-space reports and consider targets beyond local visibility |

Reports described occupancy at the time they were received. Drivers still travelled to a chosen space and attempted a claim on arrival. A free-space report did not reserve the space.

The information condition can be selected with --information-mode. The detailed implementation and experiment settings were documented in [the parking information design](research/parking_information_design.md).

## Step 4: Decision Models

The decision models were implemented in [panda_abm/behavior/decision](panda_abm/behavior/decision).

### M0: Deterministic Utility

The deterministic model selected the feasible space with the highest utility, subject to the acceptance threshold.

Implementation: [panda_abm/behavior/decision/deterministic.py](panda_abm/behavior/decision/deterministic.py).

### M1: Random Utility

The random utility model used softmax choice probabilities. Higher-utility spaces were more likely to be selected; the sampled offer was checked against the acceptance threshold.

Implementation: [panda_abm/behavior/decision/random_utility.py](panda_abm/behavior/decision/random_utility.py).

### M2: Cumulative Prospect Theory

The CPT model evaluated parking success/failure prospects relative to reference points. It applied value curvature, loss aversion and cumulative probability weights, compared parking with continuation, and used a softmax response rule.

Implementation: [panda_abm/behavior/decision/cpt.py](panda_abm/behavior/decision/cpt.py). Parameter sources and assumptions were recorded in [the CPT provenance document](research/cpt_parameter_provenance.md).

Shared feature construction, units and normalization were defined in [panda_abm/behavior/decision/transforms.py](panda_abm/behavior/decision/transforms.py).

## Step 5: Aisle Search, Movement And Timing

[panda_abm/environment/navigation.py](panda_abm/environment/navigation.py) built a connected aisle network from the estimated parking geometry. It connected main aisles, side corridors, access points and individual stalls.

[panda_abm/core/agent.py](panda_abm/core/agent.py) defined the individual driver agent and managed movement, observations, offer evaluation and parking attempts. It tracked elapsed search, resumed exploration after failed claims, and advanced drivers through walking, dwell, return and departure. The implemented trip sequence was:

~~~text
Arrival -> Search -> Target approach -> Parking claim
                         |
                    Failed claim -> Resume search

Successful parking -> Walk to destination -> Dwell
                   -> Return to vehicle -> Release space -> Exit

Search deadline reached -> Abandon search
~~~

[panda_abm/core/model.py](panda_abm/core/model.py) assembled the Mesa simulation from the facility, population, decision model, information service, resource manager and event logger. It managed the clock and driver activation, applied initial occupancy, and recorded system snapshots during each run.

Timing controls were separated:

| Setting | Purpose |
|---|---|
| integration_seconds | Physical update resolution |
| decision_interval_s | Time between search decisions |
| step_seconds | Output/snapshot interval |
| parking_maneuver_s | Duration included in a parking attempt |
| max_search_time_s | Elapsed search deadline |

Search time was measured from search start to parking or abandonment. It included travel, unsuccessful attempts and maneuver time. Walking used straight-line distance; vehicle travel followed the inferred graph.

## Step 6: Events, Parking Claims And Metrics

1. [panda_abm/core/events.py](panda_abm/core/events.py)

   This file recorded the simulation event stream, including arrivals, observations, candidate evaluations, selected targets, parking attempts, successful claims, releases, abandonment and state changes. Those events supplied the evidence used to reconstruct outcomes and decisions.

1. [panda_abm/core/resource_manager.py](panda_abm/core/resource_manager.py)

   This file handled parking-space claims and releases. It enforced single occupancy and recorded whether a driver successfully claimed a target or lost it before arrival.

1. [panda_abm/metrics/collector.py](panda_abm/metrics/collector.py)

   This file converted simulation events into driver outcomes, system snapshots, candidate-decision records and trajectories. It retained identifiers and timing information so that summaries could be traced back to individual runs and drivers.

1. [panda_abm/analysis/plots.py](panda_abm/analysis/plots.py)

   This file produced the standard experiment figures for search time, walking distance, chosen spaces and occupancy over time. Dedicated study scripts produced the matched-comparison and behavioral-profile figures.

1. [panda_abm/simulation/runner.py](panda_abm/simulation/runner.py)

   This file ran the selected decision models across repetitions and saved the outputs. It connected the facility, population, simulation settings, metric collection, summary tables, standard plots and JSON exports.
The driver-level outputs recorded parking success or abandonment, elapsed search, walking distance, chosen space, rejected offers and failed claims. Unobserved walking was left missing when a driver did not park.

## Step 7: Run The Synthetic Demo

Start with the small synthetic environment to check the simulation-to-output pipeline:

~~~powershell
python scripts/run_demo.py --output results/demo_research
~~~

The demo was configured to run the decision models and write metrics, plots, event logs and JSON exports.

## Step 8: Run A Walmart/PANDA Experiment

Load the facility through --facility-config and select the population size, initial occupancy, repetitions and information condition.

Example baseline:

~~~powershell
python scripts/run_experiment.py --facility-config data/lot_config.json --scenario-id walmart_baseline --population-size 48 --initial-occupancy-rate 0.35 --repetitions 10 --information-mode unaided --output results/walmart_baseline
~~~

Example crowded-lot condition:

~~~powershell
python scripts/run_experiment.py --facility-config data/lot_config.json --scenario-id walmart_crowded --population-size 80 --initial-occupancy-rate 0.80 --repetitions 10 --information-mode unaided --output results/walmart_crowded
~~~

Use --information-mode aisle or --information-mode space to run either information service. Use --seed to set the base random seed.

List all available options:

~~~powershell
python scripts/run_experiment.py --help
~~~

The general runner holds its generated population fixed across repetitions while changing the simulation seed. Dedicated study scripts below define their own replication and matching procedures.

## Step 9: Run Matched Information Comparisons

The dedicated information study compares all three information conditions within each decision model and occupancy level.

~~~powershell
python scripts/compare_parking_information.py --output results/information_reproduction
python scripts/report_parking_information.py --output results/information_reproduction
~~~

The comparison script followed these steps:

1. Generated and saved a population for each seed.
2. Reused it across the information conditions and decision models.
3. Matched the initial occupied-space IDs within each occupancy condition.
4. Ran the simulations and recorded checks, events and outcomes.
5. Saved per-driver and per-run data for paired comparisons.

The report script created summary tables, paired seed-level intervals, competition diagnostics and figures.

![Matched parking-information results showing search time, walking distance and parking success](research/paper_assets/information_figures_20261028/01_outcome_overview.png)

Panels show elapsed search for all arrivals, walking distance among parked drivers and parking success for unaided search, aisle counts and space reports. Rows represent initial occupancy levels; M0, M1 and CPT identify the decision models. Error bars show 95% seed-bootstrap intervals for condition means.

This archived pilot figure used the earlier CPT prospect specification. The versioned TCSS results linked below documented the corrected prospects and subsequent experiments.

The [expanded figure gallery](research/paper_assets/information_figures_20261028/README.md) documented 15 figures with captions, larger bold labels, PNG previews and vector PDFs. These figures were generated from the saved study outcomes; generating additional plots did not rerun the simulations.

To regenerate the expanded figures from a completed, verified study:

~~~powershell
python scripts/plot_information_results.py --source results/parking_information_20261028 --output research/paper_assets/information_figures_20261028
~~~

A smaller custom run:

~~~powershell
python scripts/compare_parking_information.py --output results/information_small --seeds 1100 1101 1102 --occupancies 0.8 0.95 --size 40 --workers 2
python scripts/report_parking_information.py --output results/information_small
~~~

Frozen study runners reject an existing design file. Use a fresh output folder for a new experiment.

## Step 10: Run Population And Behavioral-Profile Analysis

This study compares population specifications and examines patterns in realized search and walking behavior.

~~~powershell
python scripts/run_continuous_population_study.py --output results/continuous_reproduction
python scripts/analyze_continuous_population.py --output results/continuous_reproduction
python scripts/report_continuous_population.py --output results/continuous_reproduction
~~~

The simulation, analysis and reporting stages were separated. The analysis used training and held-out seeds, homogeneous controls and stability checks. Settings were documented in [the continuous population design](research/continuous_population_design.md).

## Step 11: Run Stress Tests And Model Audits

The publication audit separated simulation checks, crowded-lot sensitivity, decision mechanisms and claim-probability diagnostics.

~~~powershell
python scripts/publication_stress_audit.py --output results/audit_reproduction
python scripts/publication_pressure_audit.py --output results/audit_reproduction
python scripts/publication_mechanism_audit.py --output results/audit_reproduction
python scripts/publication_claim_calibration.py --output results/audit_reproduction
python scripts/report_publication_audit.py --output results/audit_reproduction
~~~

The historical summary-correction part of the audit report also needs the earlier continuous study or the archived historical_inputs/ directory copied into the audit output folder.

Further experimental scenarios were proposed in [the robustness scenario plan](research/robustness_scenario_plan.md). The [implemented model specification](research/publication_model_specification.md) documented the simulation rules and assumptions.

The [TCSS research plan](research/tcss/README.md) mapped the four research questions to existing evidence and proposed experiments. The [earlier preparation packet](research/tomacs/README.md) retained the related-work review, methods draft, analysis dictionary and table-generation command.

The additional TCSS conditions were implemented in [panda_abm/simulation/tcss_conditions.py](panda_abm/simulation/tcss_conditions.py). This file provided the simple-search benchmark, driver-level information adoption, timestamped delayed reports, background departures and the synthetic transfer layout. Its default conditions preserved the core model's outcomes.

[scripts/run_tcss_robustness.py](scripts/run_tcss_robustness.py) froze the experiment matrix, checked the existing control signatures and saved matched outcomes, populations, schedules, information-access assignments and event records. It also compared headless execution with live replay stepping.

[research/tcss/run_numerical80.py](research/tcss/run_numerical80.py) ran the additional 80% occupancy timing comparisons between CPT and its linear control. [research/tcss/analyze_robustness.py](research/tcss/analyze_robustness.py) checked archive hashes and generated paired effects, subgroup comparisons, robustness tables and PNG/PDF plots.

With the verified first-batch control archive available, reproduce these campaigns in fresh output folders:

~~~powershell
python scripts/run_tcss_robustness.py --output results/tcss_robustness_reproduction --workers 10
python research/tcss/run_numerical80.py --output results/tcss_numerical80_reproduction --workers 2
python research/tcss/analyze_robustness.py --input results/tcss_robustness_reproduction --addendum results/tcss_numerical80_reproduction --output research/tcss/robustness_reproduction
~~~

The [execution protocol](research/tcss/robustness_execution_protocol.md) documented the prerequisites, factors, matching rules and interpretation of each condition.

The [current TCSS results](research/tcss/robustness_results.md) mapped the completed experiments to the four research questions. The [plot gallery](research/tcss/robustness_gallery.md) provided captions, paired tables and PNG/PDF outputs.

## Step 12: Digital-Twin And Cesium Exports

[panda_abm/export/json_exporter.py](panda_abm/export/json_exporter.py) exported simulated events and trajectories. [panda_abm/twin/state.py](panda_abm/twin/state.py) built space, vehicle and system-state snapshots.

The general experiment runner saved:

~~~text
twin_exports/     Vehicle trajectories
event_exports/    Event streams
state_exports/    Final simulation states
~~~

The [Cesium platform](dashboard/README.md) displays the corrected 3D lot and supports live simulations, replay inspection, matched information comparisons and downloads. The existing Python ABM executes in a browser worker through Pyodide. Saved study results are shown separately from new exploratory comparisons. Synchronization with observed operational data remains future work.

After preparing the assets and dependencies as described in the platform guide, launch a local copy with:

~~~powershell
python scripts/download_browser_runtime.py
python scripts/build_public_platform.py
python scripts/benchmark_public_platform.py --fixtures-only
python -m http.server 8765 --bind 127.0.0.1 --directory dashboard
~~~

Open http://127.0.0.1:8765/ to configure a scenario or compare all three information conditions using matched populations and initial occupancy. The platform supports one to three decision models and up to 30 replications per condition. The [implementation evaluation](paper/platform_evaluation/REPORT.md) records verification, device timings and measurement limits. The research commands above reproduce the broader study experiments.

The separate [panda_abm/forecasting](panda_abm/forecasting) package provided forecast-provider hooks. The provider named PerfectForecastProvider reported current occupancy; it did not predict future availability. The current-information comparison used the information modes described in Step 3.

## Output Folders

The general experiment runner wrote:

~~~text
<output>/
  raw/
    events/events.csv
    agents/agent_metrics.csv
    system/system_metrics.csv
    decision_log.csv
    trajectories/trajectories.csv
  tables/model_comparison.csv
  figures/
  twin_exports/
  event_exports/
  state_exports/
~~~

The dedicated information study wrote:

~~~text
<output>/
  design.json
  source_snapshot.zip
  populations/
  initial_occupancy/
  replications/
  drivers.csv
  runs.csv
  checks.json
~~~

Reporting added summary and paired-comparison tables, figures, REPORT.md, package versions and a reproducibility bundle to the same directory.

The [paper-assets index](research/paper_assets/parking_information_20261028/README.md) documents the included figures, tables and their provenance.

## Main Metrics

Metrics were derived from logged events by [panda_abm/metrics/collector.py](panda_abm/metrics/collector.py). The general runner saved driver-level metrics in raw/agents/agent_metrics.csv and summaries in tables/model_comparison.csv. The dedicated information study saved drivers.csv, runs.csv and reporting tables in its output directory.

### Driver Outcomes

| Field | Meaning and unit |
|---|---|
| parked, abandoned | Whether the driver successfully parked or abandoned the search. Parking success was established by a ParkingStarted event. |
| search_time | Elapsed seconds from search start to parking or abandonment, including aisle travel, target approach, failed claims and maneuver time. |
| search_started_s, search_ended_s, parking_time_s | Simulation timestamps in seconds, retained to check the timing of each outcome. |
| search_distance | Vehicle distance travelled during search and approach, measured in metres. |
| walking_distance | Straight-line distance in metres from the chosen space to the driver's destination door. It was recorded only for drivers who parked. |
| chosen_space, chosen_module | Identifiers of the successfully selected stall and its parking module. These were left missing for unsuccessful drivers. |
| rejected_spaces, candidate_evaluations | Counts of rejected offers and evaluated candidates. These described decision activity, rather than distinct visited stalls. |
| module_switches | Number of recorded changes between parking modules during search. |
| lost_space_events | Number of failed claims where a target could not be secured. |
| violation | Recorded indicator of a parking-rule violation. |
| utility_of_chosen_action | Model-specific value recorded for the chosen action. Its scale depended on the decision model. |
| information_reports_received | Number of information reports received during the trip. |
| information_route_changes | Number of recorded exploration-route changes under the information service. |
| remote_targets_selected | Number of targets selected beyond local visibility using individual-space information. |

Run identifiers, scenario, seed, replication, driver ID, decision model and information condition accompanied the outcomes. Driver preferences, reference points and CPT parameters were also retained to relate observed decisions to the sampled inputs.

### System And Decision Records

System snapshots recorded occupied_spaces, usable_spaces, occupancy_rate, active_searchers, targeting_agents, parked_agents and abandoned_agents at timestep_s. Occupancy described the facility state, including initially occupied spaces; it differed from the success rate of the arriving study drivers.

The decision log recorded each evaluated space, its feasibility, utility, selection probability and chosen indicator. Trajectories recorded time, driver state, local x/y coordinates, selected space and candidate IDs. These records allowed search routes and individual decisions to be inspected alongside the aggregate metrics.

### Summary And Comparison Metrics

The general summaries reported success rate, abandonment rate, mean/median/90th-percentile search time, mean walking distance, mean search distance and mean rejected offers. Search summaries included all arriving drivers with recorded outcomes; walking summaries included only parked drivers because unsuccessful walking distances were missing.

The matched information report also separated search time for all arrivals from search time among parked drivers. It reported intended-exit distance among parked drivers, failed claims per driver, selected-space agreement, target competition, and outcomes by mobility constraints, destination door and intended exit. Exit distance represented straight-line proximity to the intended access point, rather than the time required to drive out.

Paired contrasts were calculated as differences within matched seeds, with 95% seed-bootstrap intervals. Walking and exit-distance contrasts were conditional on parking, so they were interpreted alongside success and abandonment rather than as outcomes for every arrival.

## Verify The Code

Run the test suite before experiments:

~~~powershell
python -m pytest tests -q
~~~

Tests cover domain rules, decision calculations, search timing, resource claims, information boundaries, population generation and analysis safeguards.
