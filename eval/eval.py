import os
import json
import time
from openai import AzureOpenAI
import re
from tabulate import tabulate
from dotenv import load_dotenv

def write_testruns_to_file(testruns):
    # Define the folder path
    folder_path = "testruns_output"

    # Check if the folder exists, if not, create it
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)

    # Define the file path within the folder
    filename = os.path.join(folder_path, time.strftime("%Y%m%d-%H%M%S") + ".json")

    # Write the array of dictionaries to the file
    with open(filename, "w") as file:
        json.dump(testruns, file, indent=4)

    print(f"Data written to {filename}")

def extract_json_from_markdown(markdown_str):
    # Regular expression to find JSON block within Markdown
    json_match = re.search(r'```json(.*?)```', markdown_str, re.DOTALL)
    if json_match:
        json_str = json_match.group(1).strip()
        return json_str
    return markdown_str

def validate_plan(created_plan, expected_plan):
    # Load the plans from JSON strings if they are in string format
    if isinstance(created_plan, str):
        created_plan = json.loads(created_plan)
    if isinstance(expected_plan, str):
        expected_plan = json.loads(expected_plan)

    # Extract commands from the plans
    created_commands = created_plan.get("commands", [])
    expected_commands = expected_plan.get("commands", [])

    # Extract expected DO actions and SAY commands
    expected_do_commands = [cmd for cmd in expected_commands if cmd['type'] == 'DO']
    expected_say_commands = [cmd for cmd in expected_commands if cmd['type'] == 'SAY']

    # Check for DO actions in created plan
    found_do_commands = 0
    for expected_command in expected_do_commands:
        action_found = False
        for created_command in created_commands:
            if (created_command['type'] == 'DO' and 
                created_command['action'] == expected_command['action']): #and 
                #created_command['parameters'] == expected_action['parameters']):
                found_do_commands += 1
                break

    # Check for SAY command in created plan
    found_say_commands = 0
    for expected_say_command in expected_say_commands:
        action_found = False
        for created_command in created_commands:
            if (created_command['type'] == 'SAY'): 
                found_say_commands += 1
                break

    # Calculate similarity score
    similarity_score = (found_do_commands + found_say_commands) / (len(expected_do_commands) + len(expected_say_commands))
    return similarity_score

load_dotenv("../.env")
endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com/")
api_key = os.getenv("AZURE_OPENAI_KEY", "abcd")
deployment = os.getenv("DEPLOYMENT_NAME", "gpt-4o")

planLocation = "../src/prompts/sequence/" 
startMsg = "Return a JSON object that uses the SAY command to say what you're thinking."
sequenceString = "Use the actions above to create a plan in the following JSON format: "
samplePlan = {"type":"plan","commands":[{"type":"DO","action":"<name>","parameters":{"<name>":"<value>"}}, {"type":"SAY","response":"<response>"}]}

client = AzureOpenAI(
    azure_endpoint=endpoint,
    api_key=api_key,
    api_version="2024-02-01",
)

# Read the config object from config.json
with open(f'{planLocation}/config.json', 'r') as config_file:
    config = json.load(config_file)

with open(f'{planLocation}/actions.json', 'r') as file:
    actionsString = file.read()

with open(f'{planLocation}/skprompt.txt', 'r') as file:
    promptString = file.read()

with open('prompt_inputs.json', 'r') as file:
    promptInputs = json.load(file)

# Replace the placeholders in the prompt string
for key in promptInputs:
    promptString = promptString.replace("{{" + key + "}}", promptInputs[key])
print (promptString)

# Create the string for the sequence prompt
sequenceString = sequenceString + json.dumps(samplePlan)

# Create the system message
systemMsg = startMsg + "\n" + actionsString + "\n" + sequenceString + "\n" + promptString

# Open the file with test inputs and expected plans
with open('test_plan.json', 'r') as file:
    test_plan = json.load(file)


# Execute testruns
testruns = []
counter = 0
for test in test_plan:
    print ('Processing input: ', test.get('input'))
    # Record the start timecls
    start_time = time.time()
    
    completion = client.chat.completions.create(
        model=deployment,
        messages= [
            {
                "role": "system",
                "content": systemMsg
            },
            {
                "role": "user",
                "content": test.get('input')
            }
        ],
        max_tokens=config['completion']['max_tokens'],
        temperature=config['completion']['temperature'],
        top_p=config['completion']['top_p'],
        frequency_penalty=config['completion']['presence_penalty'],
        presence_penalty=config['completion']['frequency_penalty'],
        stop=None,
        stream=False
    )
    # Record the end time
    end_time = time.time()
    
    # get created_plan and expected_plan json
    created_plan = extract_json_from_markdown(completion.choices[0].message.content)
    expected_plan = test.get('expected_plan')

    # Calculate the elapsed time
    elapsed_time = end_time - start_time

    # Determine resemblance to expected plan
    similarity_score = validate_plan(created_plan, expected_plan)
    if (similarity_score < 1):
        # Print the created plan and the expected plan
        print ("Created plan: ")
        print (created_plan)
        print ("Expected plan: ")
        print (expected_plan)
        print ()

    # add testrun to testruns
    if (completion.usage):
        usage = {
            "total_tokens": completion.usage.total_tokens,
            "prompt_tokens": completion.usage.prompt_tokens,
            "completion_tokens": completion.usage.completion_tokens
        }
    testrun = {
        "input": test.get('input'),
        "created_plan": created_plan,
        "expected_plan": expected_plan,
        "usage": usage,
        "elapsed_time": elapsed_time,
        "similarity_score": similarity_score
    }
    testruns.append(testrun)

    # increment counter
    counter += 1

# Print testruns as a table
headers = ["Input", "Similarity Score", "Elapsed Time (sec)", "Total Tokens"]
rows = [
    [testrun["input"], testrun["similarity_score"], f'{testrun["elapsed_time"]:.1f}', testrun["usage"]["total_tokens"]]
    for testrun in testruns
]
print(tabulate(rows, headers=headers, tablefmt="grid"))

# Write testruns to file
write_testruns_to_file(testruns)

