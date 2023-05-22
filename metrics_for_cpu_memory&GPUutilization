#Show hardware metrics per job (e.g. CPU, memory, and GPU utilization)
#written by Adesoji Alu

import psutil
import subprocess
import time
import docker

# CPU metrics
cpu_percent = psutil.cpu_percent()
cpu_count = psutil.cpu_count()
cpu_stats = psutil.cpu_stats()

# Memory metrics
memory = psutil.virtual_memory()
memory_percent = memory.percent
memory_used = memory.used
memory_available = memory.available

# GPU metrics
command = 'nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits'
result = subprocess.run(command, capture_output=True, text=True, shell=True)
gpu_utilization = result.stdout.strip()



# Print metrics
print("CPU Utilization:", cpu_percent)
print("CPU Count:", cpu_count)
print("CPU Stats:", cpu_stats)
print("Memory Utilization:", memory_percent)
print("Memory Used:", memory_used)
print("Memory Available:", memory_available)
print("GPU Utilization:", gpu_utilization)
print("Total Runtime:", runtime, "seconds")
