#Show hardware metrics per job (e.g. CPU, memory, and GPU utilization) #82
#This code is written by Adesoji Alu

#Working
import datetime
import subprocess

# Remove the existing container if it exists
container_name = 'test'
remove_command = ['docker', 'rm', '-f', container_name]
subprocess.run(remove_command)

# Run the Docker container
run_command = ['docker', 'run', '--name=' + container_name, 'alpine', 'ping', '-c', '10', '8.8.8.8']
subprocess.run(run_command)

# Get container information
container_info_command = ['docker', 'container', 'inspect', container_name]
result = subprocess.run(container_info_command, capture_output=True, text=True)
container_info = result.stdout.strip()

# Parse the container information
start_time_str = container_info.split('"StartedAt": "')[1].split('Z"')[0]
end_time_str = container_info.split('"FinishedAt": "')[1].split('Z"')[0]

# Remove the additional value after milliseconds
start_time_str = start_time_str.split('.')[0] + 'Z'
end_time_str = end_time_str.split('.')[0] + 'Z'

# Convert timestamps to datetime objects
start_time = datetime.datetime.strptime(start_time_str, '%Y-%m-%dT%H:%M:%SZ')
end_time = datetime.datetime.strptime(end_time_str, '%Y-%m-%dT%H:%M:%SZ')

# Calculate the duration in seconds
duration = (end_time - start_time).total_seconds()

# Print the duration
print("Duration:", duration, "seconds")
