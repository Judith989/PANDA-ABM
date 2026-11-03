# Platform dependencies and map attribution

The platform executes the PANDA Python source in a Pyodide Web Worker. The
engine manifest records source hashes, runtime hashes and vendored versions.
The source archive contains unchanged Mesa, NetworkX and tqdm packages and
their available distribution license files. NumPy, pandas and SciPy wheels
are official Pyodide 314.0.7 builds; wheel contents retain their licenses.
Pyodide is distributed under MPL-2.0; see https://github.com/pyodide/pyodide.

CesiumJS 1.127 is Apache-2.0 software: https://github.com/CesiumGS/cesium.
Imagery is provided by OpenStreetMap and its contributors, with attribution
shown by Cesium. The platform does not claim ownership of third-party imagery.

The parking configuration is an estimated research reconstruction. The reused
building and pavement models provide approximate visual context; corrected
space coordinates determine the simulated inventory. They are not survey data.
