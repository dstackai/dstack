import re

def execute_with_groups(commands):
    group_pattern = re.compile(r'echo "::group::(.+)"')
    end_group_pattern = "echo \"::endgroup::\""
    inside_group = False
    group_title = None

    for command in commands.splitlines():
        if group_pattern.match(command):
            inside_group = True
            group_title = group_pattern.match(command).group(1)
            print(f"\n--- {group_title} ---")
        elif command == end_group_pattern:
            inside_group = False
            group_title = None
            print("--- End of Group ---\n")
        else:
            if inside_group:
                print(f"[{group_title}] {command}")
            else:
                print(command)

# Example usage
# commands = '''
# echo "::group::My title"
# echo "Inside group"
# echo "::endgroup::"
# echo "Outside group"
# '''
# execute_with_groups(commands)


