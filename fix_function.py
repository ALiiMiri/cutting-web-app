"""
This script moves the add_default_options_if_needed function before the initialize_database function 
in the cutting_web_app.py file, then removes the duplicate function from the end of the file.
"""

import re

# Read the cutting_web_app.py file
with open('cutting_web_app.py', 'r', encoding='utf-8') as file:
    content = file.read()

# Extract the function definition
function_pattern = r'def add_default_options_if_needed\(\):[\s\S]+?if conn:\s+conn\.close\(\)'
function_match = re.search(function_pattern, content)

if function_match:
    function_code = function_match.group(0)
    
    # Position to insert before initialize_database
    insert_pattern = r'def initialize_database\(\):'
    insert_match = re.search(insert_pattern, content)
    
    if insert_match:
        insert_pos = insert_match.start()
        
        # Remove function from original position
        modified_content = content[:function_match.start()] + content[function_match.end():]
        
        # Add function before initialize_database
        modified_content = (
            modified_content[:insert_pos] + 
            function_code + 
            "\n\n\n" + 
            modified_content[insert_pos:]
        )
        
        # Write the modified content back to file
        with open('cutting_web_app.py', 'w', encoding='utf-8') as file:
            file.write(modified_content)
            
        print("Function moved successfully!")
    else:
        print("Could not find initialize_database function.")
else:
    print("Could not find add_default_options_if_needed function.") 