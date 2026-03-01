import os
import sys
import traci

if 'SUMO_HOME' in os.environ:
    sumo_home = os.environ['SUMO_HOME']
else:
    # Fallback to the default installation path if the environment variable is not set
    sumo_home = r'C:\Program Files (x86)\Eclipse\Sumo'
    os.environ['SUMO_HOME'] = sumo_home

tools = os.path.join(sumo_home, 'tools')
if os.path.exists(tools):
    sys.path.append(tools)
else:
    sys.exit(f"Could not find SUMO tools at {tools}. Please check your SUMO installation.")

sumoBinary = os.path.join(sumo_home, 'bin', 'sumo.exe')
sumoCmd = [sumoBinary, "-c", "simulation/junction.sumocfg"]

print("Connecting to SUMO...")
traci.start(sumoCmd)
print("Connected!")

step = 0
while step < 100:
    traci.simulationStep()
    if step % 10 == 0:
        # Get all traffic light IDs
        tls_ids = traci.trafficlight.getIDList()
        for tls_id in tls_ids:
            phase = traci.trafficlight.getPhase(tls_id)
            print(f"Step {step}: Traffic Light {tls_id} Phase: {phase}")
    step += 1

traci.close()
print("Simulation finished and connection closed.")