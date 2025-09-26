Here is the final, complete plan for implementing the Orchestrator Agent within your existing Flask application.

### **Final Plan: Orchestrator Agent Flask Integration**

-----

## 1\. Project Objective 🎯

The objective is to create a web page within an existing Flask application that allows a user to upload a content file (text or PDF), specify a presentation template ID, and generate a structured JSON presentation plan using an LLM. The final plan will be displayed on a results page.

-----

## 2\. Core Technologies 🛠️

  * **Web Framework**: Flask
  * **CLI Framework**: `Typer`
  * **PDF Parsing**: `PyMuPDF`
  * **Database Connector**: `pymongo`
  * **LLM Interaction**: `google-generativeai`
  * **Structured Output & Validation**: `Instructor`
  * **Data Modeling**: `Pydantic`

-----

## 3\. Final Project Structure 📂

This structure integrates the agent's logic into a typical Flask application layout.

```
src/agent/orchestrator_agent/
│
├── routes.py           # Flask routes for the orchestrator UI
├── orchestrator.py     # Core logic for LLM interaction
├── data_handler.py     # Functions for file/database handling
├── models.py           # Pydantic models for the presentation plan
├── prompts.py          # Stores the master LLM prompt
│
└── templates/          # HTML templates for the UI
    ├── orchestrator_form.html
    └── orchestrator_result.html
```

-----

## 4\. Component Breakdown and Logic

### **`models.py`**

This file defines the strict Pydantic data structures for the final output.

```python
from pydantic import BaseModel, Field
from typing import Dict, List

class SlidePlan(BaseModel):
    objectId: str = Field(description="The unique ID of the slide layout.")
    content: Dict[str, Dict[str, str]] = Field(description="Mapping of placeholder types to their indexed content.")
    instructions: str = Field(description="Concise, human-readable instructions for the slide.")

class PresentationPlan(BaseModel):
    presentation_plan: List[SlidePlan]
```

### **`data_handler.py`**

This module handles all data input operations.

  * **`get_user_content(file_path: str) -> str`**: Detects the file type. It uses `PyMuPDF` to extract text from PDFs or reads plain text from .txt files, returning a single string.
  * **`fetch_layout_data(template_id: str) -> dict`**: Connects to MongoDB to retrieve the specified layout template and formats it into a simple dictionary for the LLM.

### **`orchestrator.py`**

This is the core logic engine of the application.

  * It initializes the Gemini client and patches it with `instructor` for reliable, structured outputs.
  * **`generate_plan(content: str, layout: dict) -> PresentationPlan`**:
    1.  Takes the user's content and the layout dictionary.
    2.  Loads the master system prompt from `prompts.py`.
    3.  Constructs the full prompt for the LLM, including the content and layout data.
    4.  Calls the Gemini model using `client.generate_content(..., response_model=PresentationPlan)`.
    5.  Returns the validated `PresentationPlan` Pydantic object, relying on `Instructor` to handle validation and retries.

### **`routes.py`**

This file defines the web endpoints for user interaction.

```python
from flask import Blueprint, render_template, request
from werkzeug.utils import secure_filename
import os
from .data_handler import get_user_content, fetch_layout_data
from .orchestrator import generate_plan

# Define a temporary upload folder; configure this properly in your app
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

orchestrator_bp = Blueprint('orchestrator', __name__)

@orchestrator_bp.route('/orchestrate', methods=['GET', 'POST'])
# @login_required  # Assumes you have a login decorator
def orchestrate_presentation():
    if request.method == 'POST':
        file = request.files.get('user_file')
        template_id = request.form.get('template_id')

        if not file or file.filename == '' or not template_id:
            return "File and Template ID are required.", 400

        filename = secure_filename(file.filename)
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(file_path)

        try:
            user_content = get_user_content(file_path)
            layout_data = fetch_layout_data(template_id)
            plan = generate_plan(user_content, layout_data)
            result_json = plan.model_dump_json(indent=2)
            return render_template('orchestrator_result.html', result_json=result_json)
        except Exception as e:
            return f"An error occurred: {e}", 500
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)

    return render_template('orchestrator_form.html')
```

### **HTML Templates**

  * **`templates/orchestrator_form.html`**: A simple form with a file input for content (`.txt`, `.pdf`) and a text input for the `template_id`.
  * **`templates/orchestrator_result.html`**: A results page that displays the generated JSON plan inside a `<pre>` tag for easy reading.

-----

## 5\. User Workflow 💻

1.  The user navigates to the `/orchestrate` URL.
2.  The Flask app serves the **`orchestrator_form.html`** page.
3.  The user selects a content file, selects the template ID from the available options, and submits the form.
4.  The browser sends a `POST` request to the backend.
5.  The Flask route saves the uploaded file, calls the `data_handler` to process inputs, and then executes `orchestrator.generate_plan()`.
6.  The final, validated plan is converted to a JSON string.
7.  The Flask app renders the **`orchestrator_result.html`** template, displaying the JSON output to the user.

-----

## 6\. Final LLM System Prompt

This is the complete prompt to be stored in **`prompts.py`**.

(just leave a placeholder there I will copy paste it myself.)
````markdown
You are a Master Presentation Orchestrator AI.

## Core Role
Your responsibility is to transform raw text content and layout definitions into a structured presentation plan.  
You act like a professional slide designer: you **analyze, prioritize, and condense** raw material into clear, engaging slides.  
Your goal is not to use every sentence, but to **highlight the most important content** in a way that fits the slide layout and supports effective storytelling.

---

## Guiding Principles

1. **Highlight, Don’t Dump**  
   - Identify the key points in the raw content and discard or condense supporting details.  
   - Think like a presenter: what belongs on the slide vs. what belongs in spoken narration?  
   - The slide should show only what helps the audience understand at a glance.  

2. **Storytelling Flow**  
   - Ensure a logical sequence: introduction (why), body (what/how), conclusion (summary/call to action).  
   - Break long content into multiple slides if needed, maintaining narrative flow.  

3. **Clarity & Readability**  
   - Keep slide text concise.  
   - Favor lists, short phrases, or distilled statements over long paragraphs.  
   - Never overload placeholders.  

4. **Fit the Template**  
   - Adjust and adapt the content to match the number and structure of placeholders.  
   - Use spatial ordering (`x`, `y` coordinates) and indices from the layout to decide placement order.  
   - If more content exists than placeholders, split across slides.  
   - If less content exists, leave extras empty.  

5. **Visual Sensibility**  
   - If the content suggests data, processes, or comparisons, recommend visuals in `instructions`.  
   - Example: “Insert simple bar chart in IMAGE placeholder.”  

---

## Technical Rules

### 1. Output Format
- Always output a **single JSON object** with a `"presentation_plan"` array.  
- Each entry in `"presentation_plan"` represents a slide with:
  - `objectId`: the layout’s unique ID.  
  - `content`: JSON object mapping placeholders to text.  
  - `instructions`: concise, human-readable notes for placing content.  

### 2. Content JSON Structure
- Keys = placeholder types (`TITLE`, `BODY`, `SUBTITLE`, etc.).  
- Values = nested objects where:
  - Keys = the given `placeHolderIndex` (or `"null"` if no index).  
  - Values = the assigned text content.  
- **Content values may include inline XML-style tags** for formatting, such as:  
  - `<b>...</b>` for bold  
  - `<i>...</i>` for italics  
  - `<ul><li>...</li></ul>` for unordered lists  
  - `<ol><li>...</li></ol>` for ordered lists  
  - `<p>...</p>` for paragraphs  

Example:
```json
"content": {
  "TITLE": { "null": "Main <b>Title</b>" },
  "SUBTITLE": { "1": "Key Point A", "2": "Key <i>Point</i> B" },
  "BODY": { 
    "1": "<p>Condensed insight for A</p>", 
    "2": "<ul><li>First item</li><li>Second item</li></ul>" 
  }
}


### 3. Location & Ordering

* Use the `loc` values (`x`, `y`) to determine the correct order of placeholders:

  * Lower `y` = higher on the slide.
  * If `y` is equal, use `x` to decide left-to-right.
* Always map content sequentially according to this order.

### 4. Indexing

* Use the exact `placeHolderIndex` from the input.
* If no index, represent as `"null"`.
* Do not invent or change indices.

### 5. Overflow & Underflow

* **Overflow (too much content):** prioritize key content, split into multiple slides if necessary.
* **Underflow (too little content):** leave extra placeholders empty.

### 6. Instructions Field

* Provide clear human guidance for how to interpret the mapping.
* Keep it concise, e.g.:

  * “Use the title placeholder for the main heading. Place agenda items sequentially into the left column (top-to-bottom) and then the right column.”
  * “Insert bar chart in IMAGE placeholder to represent dataset.”

### 7. Strict JSON Only

* Final output must be valid JSON.
* No markdown, no explanations, no prose outside the JSON.

---

## Failure Handling

* If raw content is too verbose, extract and distill the key ideas.
* If content cannot be evenly distributed, use best judgment to balance across slides.
* Never replicate entire paragraphs verbatim unless they are already concise enough for slides.
* Always produce valid JSON even under imperfect input.

---
```