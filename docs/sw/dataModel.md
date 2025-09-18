# Data Model
## Database Schema Overview
Our database consists of the following main collections:
* `users`: Stores information about our application's users, including their authentication details.
* `presentations`: Stores the complete JSON data from the Google Slides API for each presentation, along with our own custom metadata.
* `tasks`: stores the the tasks that the planer plans to complete. Each entry will be a task
* `conversations`: This will be used to maintain conversation history for the users 

```mermaid
erDiagram
    users {
        string _id PK "User ID"
        object userdata
    }

    presentations {
        string _id PK "Presentation ID"
        string ownerId FK "User ID"
        object presentationData
    }

    conversations {
        ObjectId _id PK "Conversation ID"
        string userId FK "User ID"
        string presentationId FK "Presentation ID"
        array messages
    }

    tasks {
        ObjectId _id PK "Task ID"
        string userId FK "User ID"
        string presentationId FK "Presentation ID"
        ObjectId conversationId FK "Conversation ID"
        string description
        string status
    }

    users ||--o{ presentations : "owns"
    users ||--o{ conversations : "has"
    presentations ||--o{ conversations : "is discussed in"
    users ||--o{ tasks : "assigned"
    presentations ||--o{ tasks : "relates to"
    conversations ||--o{ tasks : "generates"
```

*this table has been abstracted for simplicity