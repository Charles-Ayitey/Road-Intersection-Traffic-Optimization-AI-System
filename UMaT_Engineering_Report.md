# UMaT Engineering Report

## Recent Changes
- **Date**: 2026-04-15
- **Files Modified**: 
  - `api/main.py`
- **Issue/Feature Description**: Added local data persistence structure to log live simulation traffic counts, AI phases, and modes instead of immediately wiping history upon process stop.
- **Change Applied**: Added an `sqlite3` integration to create and insert records into `data/traffic_history.db` whenever a new batch of vehicular counts is parsed from `VisionUpdate` on the `/update_counts` endpoint.
- **Status**: Completed without impacting other running loops.

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

