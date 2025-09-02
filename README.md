# Slide Agent
## Goal 
Given a template and some content automatically convert the content into slides in the format of the template.

## High Level Architechture
To achive this we will be using the following high level architecture
<!-- ![ALt text](./docs/sw/high_level_overview.png ) -->
![alt text](docs/sw/high_level_overview.png)
The system starts off with the user giving the system a template they want to build their ppt in, we pass it to an llm to understand all the layouts on the slides and we write textual explainations for our orchestrator.

The Orchestrator is the main brain of the system it will take in the users content and textual descriptions of the layouts, first it will create a plan where it will organize the content into slides and also output the layout to use out of all the available options. In the plan it will also mention what content goes into which type of layout box (the title will go to the title). The user will need to approve the plan  or give the agent feedback to improve the design. After the plan is approved the orchestrator will start adding slide make requests to the queue. We will be able to make the worker agents work on a single slide in parallel. 

The worker agent will recive all the relevent context related to the slide only, it will convert the plan for that slide to tool calls. Because the process is not that complicated and the orechestrator did all the heavy work the worker will make sure that the request that the orchestrator made is correct If there are any errors it will correct the request. It will try the api call for a max of 5 times. It will let the orchestrator know weather it failed or passed with an explaination of what it did.

If the request passed the user will be told to check the slide and asked to give feedback. If the operations did not work the user will have the choice to tell the agent what to do or make the failed slides personally.

To make sure that a check is kept on the progress the orchestrator will maintain a tasklist which it will update based on the feedback from the worker and human.

## [data model](./docs/sw/dataModel.md)
The  data will be stored in a mongo DB