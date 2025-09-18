The whole flow starts off with doing Oauth, making sure that we can access the users google slides. The instructions to that are in @OauthInstructions.md
Once the  Oauth is complete, the user will be asked to add a template in which he would like to make a presentation

we would take that template presentation and understand the layout using the layout understanding llm more of which is described in the other documents.
We will do this for  each layout in this template one by one
store all this information in a database (we can decide which one we want later)

Now the user  will get a chance to input the content which can be a text file or a pdf or a markdown the planer agent will get the slide layouts, layout explainations, content and it will plan out how it to make the presentation and show a plan to the user, once the user approves the plan after some iterations the agent breaks down the whole plan into slide wise tasks updates the todo list. Then send the tasks to queue. When making a new slide using a layout we can specify the object ID's of each object that was already present in the layout. We can generate the stating part of those object ids and make it globally unique but just adding a prefix of the slide number. So the planer agent will generate object ID's like textbox_1 but it will actually be sld_1_textbox_1

The worker agents can take the tasks of the queue and work on them, they will convert the tasks to tool calls with proper template understanding, once the internal validations pass the api calls are executed, if the call fails the worker is givien the error and asked to improve, else it is told that success is acheived and the worker replies to the main agent that the work is complete and what was accomplished.

The planer agent recives the update and updates the user that some work is done(doesnt need llm internvention can just be a message that uses the udpate from the worker agent to let the user know) the user will then check and either approve the slide or provide changes. Based on the user response the planer agent will update the todo list and it will also add an update task to the list

If an update task goes to the worker agent the flag will be up in which case the worker agent will need to be provided with the current state of the slide as well.