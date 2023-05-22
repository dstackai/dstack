import argparse
import dstack

# Parse command-line arguments
parser = argparse.ArgumentParser()
parser.add_argument('--yes', '-y', action='store_true', help='Auto-confirm the run')
args = parser.parse_args()

# Define the jobs and instance types
jobs = [
    {
        'name': 'Job 1',
        'instance_type': 'c5.large'
    },
    {
        'name': 'Job 2',
        'instance_type': 'm5.large'
    },
    {
        'name': 'Job 3',
        'instance_type': 'r5.large'
    }
]

# Show the plan
print("Plan:")
for job in jobs:
    print(f"- Job: {job['name']}, Instance Type: {job['instance_type']}")

# Ask for confirmation unless auto-confirmed
if not args.yes:
    confirmation = input("Confirm the run (yes/no): ")
    if confirmation.lower() != 'yes':
        print("Run cancelled.")
        exit()

# Run the jobs
for job in jobs:
    # Code to execute each job
    print(f"Running {job['name']} on {job['instance_type']}...")

print("All jobs completed.")
