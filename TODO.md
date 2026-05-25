# add text pre-processing to TTS to make it sound better:

- avoid (s)
- detect filenames and make for instance "foo.bar" be "foo dot bar"
- strip emojis
- strip markdown (eg: **foo** => foo) or speak it loud "title XXXX"
- and so on...

# Experiment with and without tool suggestion

- the manager suggests a tool when asking the worker, try to benchmark with and without it, it could be an unnecessary complexity.

# Restrict the manager more and specialize workers (to be refined)

- Make the manager only delegate and read file snippets or get file status
- Allow "types" of delegates, which having their state machine / prompt
    - "default worker agent" (what we have now, no state machine)
    - "dev team" : analyst analyze the request and assess the impact on the code -> dev implement the change -> test verify the change corresponds to the request
        - if any implementation fails it returns to the analyst providing the previous context
    - "tester": first understand what are the testing capabilities available for the given task, then execute the tests and provide the feedback: failed or success or error (couldn't test)
    - "project manager": break down a complex request into subtasks, delegate each of them one by one, ask a tester to verify each time, evaluate the overall result of each step to decide to re-do it or keep it and switch to the next one
    - "researcher": first collects all the valid sources for a given research, then delegate each item to a different worker and get the results. Then make a study of the results to provide an overview and the best insights

# Add a generic verification task

- spawn a worker to review and challenge the changes made for the given task
- A software expert should decide if it's worth it
- if it's worth it, revert the implementation and start with the new idea

# Smarter tool compaction

- experiment showing only the tool result with a clear header instead of all the tool call history/complexity (should be a flag experimental.tool_compact)
