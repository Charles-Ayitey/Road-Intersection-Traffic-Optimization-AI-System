# UMaT Engineering Report

## Recent Changes
- **Date**: 2026-04-15
- **Files Modified**: 
  - `api/main.py`
- **Issue/Feature Description**: Added local data persistence structure to log live simulation traffic counts, AI phases, and modes instead of immediately wiping history upon process stop.
- **Change Applied**: Added an `sqlite3` integration to create and insert records into `data/traffic_history.db` whenever a new batch of vehicular counts is parsed from `VisionUpdate` on the `/update_counts` endpoint.
- **Status**: Completed without impacting other running loops.

- **Date**: 2026-04-15
- **Files Modified**: 
  - `ai_agent/live_controller.py`
  - `dashboard/app.py`
  - `simulation/junction.sumocfg`
  - `simulation/rl-tests.sumocfg`
  - `simulation/junction.rou.xml`
  - `ai_agent/sumo_env.py`
- **Issue/Feature Description**: Added asynchronous quick-override and starvation checking pipelines to the AI controller. Enhanced SUMO GUI visualization loop interpolations and collision avoidance for presentation polish.
- **Change Applied**: 
  - Enabled API interception in `live_controller.py` to command fixed 15s phases based on `active_override` flags.
  - Implemented real-time Starvation tracking in `app.py` UI alongside quick-response Emergency priority buttons. 
  - Decreased SUMO step simulation length to 0.1s for extreme buttery smoothing (`--step-length 0.1`), configured cars to `IDM` (Intelligent Driver Model) for realistic compression, and completely disabled magical teleportation (`--time-to-teleport -1`).
- **Status**: Live operator overrides work without disconnecting AI mode completely. SUMO visual simulation appears entirely cinematic and stutter-free.

## Previous Changes
- **Date**: 2026-04-15
- **Files Modified**: 
  - `launch_system.py`
  - `config.json`
- **Issue Description**: The supervisor script `launch_system.py` was swallowing crash logs by piping stdout/stderr to `.DEVNULL`. Without logs, the system appeared "broken" and was unreachable because the vision module was trying to connect to a hardcoded local IP webcam (`https://10.143.147.193:4343/video`).
- **Fix Applied**: 
  - Modified `launch_system.py` to pipe logs gracefully.
  - Switched `active_scenario` in `config.json` from `"live_camera"` to `"traffic_test"` to ensure video loops successfully processed simulated dataset videos rather than timing out attempting to catch a live IP camera. 
- **Status**: The supervisor script starts successfully, and the system connects to the API properly.
