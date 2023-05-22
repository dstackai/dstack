#Working Code

#Import Libraries
import datetime
import subprocess
import docker

container_id = '0357068ca174e714ff4c64d5e3e0e7c11dbd7715f61d1069c726b001584dd6fa'  # Replace <container_id> with your container ID

# Get container information
container_info_command = ['docker', 'container', 'inspect', container_id]
result = subprocess.run(container_info_command, capture_output=True, text=True)
container_info = result.stdout.strip()
print(container_info)


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
