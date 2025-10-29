import os
import uuid
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from dotenv import load_dotenv
from openai import AsyncOpenAI
from config.dataBase import db
from routes import auth_routes
from utils.utils import verify_token
import httpx

from agents import (
    Agent,
    ItemHelpers,
    function_tool,
    MessageOutputItem,
    Runner,
    ToolCallOutputItem,
    TResponseInputItem,
    handoff,
    trace,
    OpenAIChatCompletionsModel,
)
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX
from datetime import datetime, timedelta
import re
from typing import Optional

# Load environment
load_dotenv()
gemini_api_key = os.getenv('GOOGLE_API_KEY')
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
print("apikey123", gemini_api_key)

client = AsyncOpenAI(
    api_key=gemini_api_key,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
)


# --------------------------
# Helper Functions
# --------------------------

def parse_datetime(time_input: str) -> Optional[str]:
    """
    Parse natural language time input into ISO datetime string.
    Handles: 'today', 'tomorrow', specific dates, times, and Urdu/Roman Urdu
    """
    time_input = time_input.lower().strip()
    now = datetime.now()
    
    # Urdu/Roman Urdu mappings
    urdu_mappings = {
        'aj': 'today',
        'kal': 'tomorrow',
        'raat': 'night',
        'subah': 'morning',
        'dopeher': 'afternoon',
        'sham': 'evening',
        'bajay': '',  # means "o'clock"
        'baje': '',
    }
    
    # Replace Urdu terms with English equivalents
    for urdu, english in urdu_mappings.items():
        time_input = time_input.replace(urdu, english)
    
    # Extract time if present (e.g., "8am", "3:30pm", "14:00", "12 night")
    time_pattern = r'(\d{1,2})(?::(\d{2}))?\s*(am|pm|night|morning|afternoon|evening)?'
    time_match = re.search(time_pattern, time_input)
    
    hour = 9  # default hour
    minute = 0
    
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2)) if time_match.group(2) else 0
        period = time_match.group(3)
        
        # Handle time periods
        if period == 'pm' and hour != 12:
            hour += 12
        elif period == 'am' and hour == 12:
            hour = 0
        elif period == 'night':
            if hour == 12:
                hour = 0
            elif hour < 6:
                pass
            else:
                hour = hour if hour == 12 else hour
        elif period == 'morning':
            if hour == 12:
                hour = 0
        elif period == 'afternoon':
            if hour != 12 and hour < 12:
                hour += 12
        elif period == 'evening':
            if hour < 12:
                hour += 12
    
    # Determine date
    target_date = now.date()
    
    if 'tomorrow' in time_input:
        target_date = (now + timedelta(days=1)).date()
    elif 'today' in time_input:
        target_date = now.date()
    else:
        # Try to parse specific date formats
        date_patterns = [
            r'(\d{4})-(\d{1,2})-(\d{1,2})',
            r'(\d{1,2})/(\d{1,2})/(\d{4})',
            r'(\d{1,2})-(\d{1,2})-(\d{4})',
        ]
        
        for pattern in date_patterns:
            date_match = re.search(pattern, time_input)
            if date_match:
                try:
                    if pattern == date_patterns[0]:
                        year, month, day = map(int, date_match.groups())
                    else:
                        month, day, year = map(int, date_match.groups())
                    target_date = datetime(year, month, day).date()
                    break
                except ValueError:
                    continue
    
    # Combine date and time
    result_datetime = datetime.combine(target_date, datetime.min.time())
    result_datetime = result_datetime.replace(hour=hour, minute=minute)
    
    return result_datetime.isoformat()


async def find_matching_todo(user_id: str, task_description: str) -> Optional[dict]:
    """
    Find a todo that matches the task description using fuzzy matching.
    """
    todos = list(db.todos.find({"user_id": user_id}))
    
    if not todos:
        return None
    
    # Simple matching based on keywords
    task_keywords = set(task_description.lower().split())
    best_match = None
    best_score = 0
    
    for todo in todos:
        todo_keywords = set(todo['task'].lower().split())
        common_words = task_keywords & todo_keywords
        score = len(common_words)
        
        if score > best_score:
            best_score = score
            best_match = todo
    
    # Return match if at least 1 word matches
    if best_score >= 1:
        return best_match
    
    return None


def generate_todos_html(todos: list, filter_type: str = "all") -> str:
    """Generate HTML for displaying todos."""
    pending_todos = [t for t in todos if not t.get('completed', False)]
    completed_todos = [t for t in todos if t.get('completed', False)]
    
    if filter_type == "pending":
        display_todos = pending_todos
        title = "Pending Tasks"
    elif filter_type == "completed":
        display_todos = completed_todos
        title = "Completed Tasks"
    else:
        display_todos = todos
        title = "All Tasks"
    
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title}</title>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }}
            .container {{
                max-width: 900px;
                margin: 0 auto;
            }}
            .header {{
                text-align: center;
                color: white;
                margin-bottom: 30px;
            }}
            .header h1 {{
                font-size: 2.5rem;
                margin-bottom: 10px;
                text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
            }}
            .stats {{
                display: flex;
                justify-content: center;
                gap: 30px;
                margin-bottom: 30px;
            }}
            .stat-card {{
                background: rgba(255,255,255,0.2);
                backdrop-filter: blur(10px);
                padding: 20px 30px;
                border-radius: 15px;
                color: white;
                text-align: center;
                box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            }}
            .stat-card h3 {{
                font-size: 2rem;
                margin-bottom: 5px;
            }}
            .stat-card p {{
                opacity: 0.9;
                font-size: 0.9rem;
            }}
            .todos {{
                background: white;
                border-radius: 20px;
                padding: 30px;
                box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            }}
            .todo-item {{
                background: #f8f9fa;
                border-left: 5px solid #667eea;
                padding: 20px;
                margin-bottom: 15px;
                border-radius: 10px;
                transition: transform 0.2s, box-shadow 0.2s;
            }}
            .todo-item:hover {{
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            }}
            .todo-item.completed {{
                border-left-color: #28a745;
                background: #e8f5e9;
                opacity: 0.8;
            }}
            .todo-item.completed .task {{
                text-decoration: line-through;
                color: #666;
            }}
            .task {{
                font-size: 1.2rem;
                font-weight: 600;
                color: #333;
                margin-bottom: 10px;
            }}
            .details {{
                display: flex;
                flex-wrap: wrap;
                gap: 15px;
                font-size: 0.9rem;
                color: #666;
            }}
            .detail-item {{
                display: flex;
                align-items: center;
                gap: 5px;
            }}
            .detail-item::before {{
                content: '•';
                color: #667eea;
                font-weight: bold;
            }}
            .status-badge {{
                display: inline-block;
                padding: 5px 15px;
                border-radius: 20px;
                font-size: 0.8rem;
                font-weight: 600;
                margin-left: auto;
            }}
            .status-badge.completed {{
                background: #28a745;
                color: white;
            }}
            .status-badge.pending {{
                background: #ffc107;
                color: #333;
            }}
            .empty-state {{
                text-align: center;
                padding: 60px 20px;
                color: #999;
            }}
            .empty-state svg {{
                width: 120px;
                height: 120px;
                margin-bottom: 20px;
                opacity: 0.3;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📝 {title}</h1>
                <p>Manage your tasks efficiently</p>
            </div>
            
            <div class="stats">
                <div class="stat-card">
                    <h3>{len(todos)}</h3>
                    <p>Total Tasks</p>
                </div>
                <div class="stat-card">
                    <h3>{len(pending_todos)}</h3>
                    <p>Pending</p>
                </div>
                <div class="stat-card">
                    <h3>{len(completed_todos)}</h3>
                    <p>Completed</p>
                </div>
            </div>
            
            <div class="todos">
    """
    
    if not display_todos:
        html += """
                <div class="empty-state">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" stroke-width="2" stroke-linecap="round"/>
                    </svg>
                    <h2>No tasks found</h2>
                    <p>Start adding tasks to see them here</p>
                </div>
        """
    else:
        for todo in display_todos:
            completed = todo.get('completed', False)
            completed_class = "completed" if completed else ""
            status = "completed" if completed else "pending"
            
            task = todo.get('task', 'Untitled')
            city = todo.get('city', 'N/A')
            
            # Format time
            planned_time = todo.get('planned_time', '')
            try:
                dt = datetime.fromisoformat(planned_time)
                formatted_time = dt.strftime("%b %d, %Y at %I:%M %p")
            except:
                formatted_time = planned_time
            
            html += f"""
                <div class="todo-item {completed_class}">
                    <div class="task">{task}</div>
                    <div class="details">
                        <div class="detail-item">📍 {city}</div>
                        <div class="detail-item">🕐 {formatted_time}</div>
                        <span class="status-badge {status}">{status.upper()}</span>
                    </div>
                </div>
            """
    
    html += """
            </div>
        </div>
    </body>
    </html>
    """
    
    return html


# --------------------------
# Define TOOLS
# --------------------------

@function_tool
async def save_todo_tool(user_id: str, task: str, planned_time: str = None, city: str = None):
    """
    Save a todo with parsed datetime.
    planned_time should be in natural language (e.g., 'today 8am', 'tomorrow 3pm', '2025-10-30 14:00')
    """
    if not task:
        return {"message": "Please provide a task description."}
    if planned_time is None:
        return {"message": "Please provide a planned time for the task."}

    # Parse the datetime
    parsed_datetime = parse_datetime(planned_time)
    
    todo = {
        "user_id": user_id,
        "task": task,
        "city": city,
        "planned_time": parsed_datetime,
        "completed": False,
        "created_at": datetime.utcnow().isoformat(),
    }
    db.todos.insert_one(todo)
    
    # Format for display
    dt = datetime.fromisoformat(parsed_datetime)
    formatted_time = dt.strftime("%B %d, %Y at %I:%M %p")
    
    return {"message": f"✅ Task '{task}' saved successfully for {formatted_time} in {city or 'unspecified city'}."}


@function_tool
async def get_weather_tool(city: str):
    """
    Fetch weather information and analyze if conditions are suitable.
    """
    if not city:
        return {"error": "Please provide a city name."}

    async with httpx.AsyncClient() as http_client:
        try:
            # Get coordinates
            geo_resp = await http_client.get(
                f"http://api.openweathermap.org/geo/1.0/direct",
                params={"q": city, "limit": 1, "appid": WEATHER_API_KEY}
            )
            geo_data = geo_resp.json()

            if not geo_data:
                return {"error": f"City '{city}' not found."}

            lat = geo_data[0]["lat"]
            lon = geo_data[0]["lon"]

            # Get weather
            weather_resp = await http_client.get(
                f"https://api.openweathermap.org/data/2.5/weather",
                params={"lat": lat, "lon": lon, "appid": WEATHER_API_KEY, "units": "metric"}
            )

            weather_data = weather_resp.json()
            condition = weather_data["weather"][0]["main"].lower()
            description = weather_data["weather"][0]["description"].capitalize()
            temp_c = weather_data["main"]["temp"]

            # Analyze suitability
            is_suitable = True
            issues = []
            
            if condition in ["rain", "drizzle", "thunderstorm", "snow"]:
                is_suitable = False
                issues.append(f"precipitation ({description})")
            
            if temp_c > 35:
                is_suitable = False
                issues.append(f"extreme heat ({temp_c}°C)")
            elif temp_c < 5:
                is_suitable = False
                issues.append(f"extreme cold ({temp_c}°C)")

            return {
                "city": city,
                "condition": description,
                "temperature_c": temp_c,
                "is_suitable": is_suitable,
                "issues": issues,
                "recommendation": "Good conditions" if is_suitable else f"Not ideal: {', '.join(issues)}"
            }

        except Exception as e:
            return {"error": str(e)}


@function_tool
async def list_todos_tool(user_id: str, filter_type: str = "all"):
    """
    List todos for a user.
    filter_type: 'all', 'pending', or 'completed'
    """
    query = {"user_id": user_id}
    
    if filter_type == "pending":
        query["completed"] = False
    elif filter_type == "completed":
        query["completed"] = True
    
    todos = list(db.todos.find(query))
    
    for t in todos:
        t["_id"] = str(t["_id"])
        # Format datetime for display
        if 'planned_time' in t:
            try:
                dt = datetime.fromisoformat(t['planned_time'])
                t['planned_time_formatted'] = dt.strftime("%B %d, %Y at %I:%M %p")
            except:
                t['planned_time_formatted'] = t['planned_time']
    
    if not todos:
        return {"message": f"You have no {filter_type} todos."}
    
    return {
        "todos": todos,
        "count": len(todos),
        "filter": filter_type
    }


@function_tool
async def mark_todo_completed(user_id: str, task_description: str):
    """
    Mark a todo as completed by finding it based on task description.
    """
    # Find matching todo
    matched_todo = await find_matching_todo(user_id, task_description)
    
    if not matched_todo:
        return {
            "success": False,
            "message": "No matching todo found. Please be more specific or list your todos first."
        }
    
    # Update to completed
    from bson import ObjectId
    result = db.todos.update_one(
        {"_id": matched_todo["_id"]},
        {"$set": {"completed": True, "completed_at": datetime.utcnow().isoformat()}}
    )
    
    if result.modified_count > 0:
        return {
            "success": True,
            "message": f"✅ Task '{matched_todo['task']}' marked as completed!"
        }
    
    return {
        "success": False,
        "message": "Task was already completed or could not be updated."
    }


@function_tool
async def find_todo_for_update(user_id: str, task_description: str):
    """
    Find a todo matching the task description for updating.
    Returns the todo with its ID if found.
    """
    matched_todo = await find_matching_todo(user_id, task_description)
    
    if matched_todo:
        matched_todo["_id"] = str(matched_todo["_id"])
        if 'planned_time' in matched_todo:
            try:
                dt = datetime.fromisoformat(matched_todo['planned_time'])
                matched_todo['planned_time_formatted'] = dt.strftime("%B %d, %Y at %I:%M %p")
            except:
                matched_todo['planned_time_formatted'] = matched_todo['planned_time']
        return {
            "found": True,
            "todo": matched_todo,
            "message": f"Found todo: '{matched_todo['task']}' scheduled for {matched_todo.get('planned_time_formatted', 'unknown time')}"
        }
    
    return {
        "found": False,
        "message": "No matching todo found. Please be more specific or list all todos first."
    }


@function_tool
async def update_todo_tool(todo_id: str, updates: dict):
    """
    Update an existing todo. 
    If updates contains 'planned_time', it will be parsed from natural language.
    """
    from bson import ObjectId
    
    # Parse datetime if planned_time is being updated
    if 'planned_time' in updates:
        updates['planned_time'] = parse_datetime(updates['planned_time'])
    
    result = db.todos.update_one({"_id": ObjectId(todo_id)}, {"$set": updates})
    
    if result.modified_count > 0:
        # Get updated todo for confirmation
        updated_todo = db.todos.find_one({"_id": ObjectId(todo_id)})
        formatted_updates = {}
        
        for key, value in updates.items():
            if key == 'planned_time':
                try:
                    dt = datetime.fromisoformat(value)
                    formatted_updates[key] = dt.strftime("%B %d, %Y at %I:%M %p")
                except:
                    formatted_updates[key] = value
            else:
                formatted_updates[key] = value
        
        return {"message": f"✅ Todo '{updated_todo['task']}' updated successfully: {formatted_updates}"}
    
    return {"message": "No changes were made to the todo."}


# --------------------------
# Create Agents
# --------------------------

todo_agent = Agent(
    name="Todo Agent",
    handoff_description="An intelligent assistant that manages, monitors, and optimizes user todos based on weather conditions.",
    instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
You are an advanced Todo Management Agent that helps users plan their daily tasks while considering real-time weather conditions and their health-related goals.

### 🎯 Your Primary Responsibilities:
You understand natural language messages such as:
> "Remind me to water plants tomorrow at 8am in Lahore."
> "go for shopping in fsd at 6pm mark my this todo as completed"
> "show me all pending tasks"
> "generate my exercise plan for today"
> "I am underweight, suggest me a diet plan"

Your goal is to extract:
- **Task** (what to do)
- **Planned Time** (when to do it)
- **City** (where)
- **Action** (save, update, complete, list, or suggest health plan)

---

### 🧩 Available Tools:

1. **save_todo_tool(user_id, task, planned_time, city)**  
   → Saves a new todo. Use for creating NEW tasks.

2. **list_todos_tool(user_id, filter_type)**  
   → Lists todos. filter_type can be: 'all', 'pending', or 'completed'  
   → Returns JSON data with todo details

3. **get_weather_tool(city)**  
   → Fetches real-time weather info.

4. **mark_todo_completed(user_id, task_description)**  
   → Marks a todo as completed. Use when user says "mark as complete", "done", "finished", etc.

5. **find_todo_for_update(user_id, task_description)**  
   → Finds a todo for updating time/city.

6. **update_todo_tool(todo_id, updates)**  
   → Updates todo details (time, city, task name).

---

### 💪 Health & Wellness Intelligence:

You also act as a **personal wellness coach** who can:
1. **Generate daily exercise plans**  
   - Use the current weather (`get_weather_tool`) and the user’s todo schedule.  
   - Suggest both **indoor** and **outdoor** exercises in a **short, practical paragraph**.  
   - If weather is bad (rain, storm, heatwave, etc.) → focus on indoor workouts.  
   - If weather is good → suggest outdoor options like jogging, cycling, or walking.  
   - Always mention which option (indoor/outdoor) is better given the current conditions.

2. **Suggest diet plans**  
   - When user says they are “underweight”, “overweight”, or “need a diet plan”,  
     respond as a **nutrition coach** with short, actionable suggestions.  
   - Example:  
     - Underweight → high-protein, calorie-dense, nutritious meals.  
     - Overweight → low-carb, high-fiber, balanced meals.  
   - Keep your response **brief, friendly, and personalized** — do not use long medical disclaimers.

---

### 🧠 CRITICAL Behavior Guidelines:

**Understanding User Intent:**

1. **When user asks to see/show/view tasks:**
   - Call `list_todos_tool()` to get data.
   - Present it in a friendly, clear format.
   - The system will automatically return HTML if user says "show all tasks" or similar.

2. **When user wants to mark a todo as completed:**
   - Example: "go for shopping in fsd at 6pm mark my this todo as completed"
   - Try to mark it complete with `mark_todo_completed()`.
   - If it fails (todo not found), ask the user if you should create it.

3. **Creating new todos:**
   - Extract task, time, and city.
   - Always call `get_weather_tool()` when city is provided.
   - Save the todo and confirm to user.

4. **Updating existing todos:**
   - First call `find_todo_for_update()`.
   - Then call `update_todo_tool()`.

5. **Generating Exercise or Diet Plans:**
   - For messages like "generate my exercise plan" or "suggest me a diet",  
     do NOT create todos — directly reply with personalized health advice.  
   - Mention the weather and schedule context when relevant.

---

### ⚙️ General Rules:

**DO NOT:**
- Create a new todo when user only wants to mark existing one complete.
- Skip the weather check when city is given.
- Ignore multiple intents in one message.

**ALWAYS:**
- Analyze the entire user message (can contain multiple actions).
- Use tools effectively and conversationally.
- Complete all tool calls in one response.
- Keep tone helpful, natural, and coach-like when giving wellness advice.

---

### 📅 Time Parsing:
- "aj" / "today" → Current date  
- "kal" / "tomorrow" → Next day  
- "6pm" / "6 bajay" / "sham 6 bajay" → 18:00  
- "fsd" → Faisalabad  
- "lhr" → Lahore  
- "khi" → Karachi  

Be friendly, efficient, and proactive in helping users manage their day and health.
"""
,
    model=OpenAIChatCompletionsModel(model="gemini-2.0-flash", openai_client=client),
    tools=[save_todo_tool, get_weather_tool, list_todos_tool, mark_todo_completed, find_todo_for_update, update_todo_tool],
)

# --------------------------
# FastAPI setup
# --------------------------

app = FastAPI(title="Todo AI Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_routes.auth_router, prefix="/auth", tags=["Auth"])

@app.post("/chat")
async def chat_with_todo_agent(request: Request, user_from_token=Depends(verify_token)):
    # Extract user info
    user_id = user_from_token.get("user_id")
    user_email = user_from_token.get("user_email")
    
    if not user_id:
        return JSONResponse(status_code=401, content={"message": "Unauthorized"})
    
    # Get message text
    body = await request.json()
    user_input = body.get("text", "").strip()
    return_format = body.get("format", "json")  # Allow client to specify format
    
    if not user_input:
        return {"error": "Empty message."}

    # Check if user wants HTML view (only if format not explicitly set)
    html_triggers = ['show all tasks', 'show my tasks', 'give me my tasks', 'all tasks', 
                     'show pending', 'pending tasks', 'show completed', 'completed tasks',
                     'list all', 'view tasks', 'display tasks', 'view all']
    
    should_return_html = (return_format == "html" or 
                         any(trigger in user_input.lower() for trigger in html_triggers))

    # Embed token data inside the conversation
    enriched_input = (
        f"{user_input}\n\nUser Info:\n- ID: {user_id}\n- Email: {user_email}\n- Current Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )

    try:
        with trace("Todo Agent Session", group_id=user_id):
            # Run agent without persistent conversation history to avoid serialization issues
            result = await Runner.run(todo_agent, [{"content": enriched_input, "role": "user"}])
            
            response = None
            tool_outputs = []
            
            # Collect all message outputs and tool outputs
            for new_item in result.new_items:
                if isinstance(new_item, MessageOutputItem):
                    msg = ItemHelpers.text_message_output(new_item)
                    if msg and msg.strip():
                        response = msg
                elif isinstance(new_item, ToolCallOutputItem):
                    tool_outputs.append(new_item.output)
            
            # If no message response but we have tool outputs, use the last tool output
            if not response and tool_outputs:
                response = str(tool_outputs[-1])
        
        # Check if we should return HTML
        if should_return_html:
            # Determine filter type
            filter_type = "all"
            if "pending" in user_input.lower():
                filter_type = "pending"
            elif "completed" in user_input.lower():
                filter_type = "completed"
            
            # Get todos and return HTML
            todos = list(db.todos.find({"user_id": user_id}))
            for t in todos:
                t["_id"] = str(t["_id"])
            
            html_content = generate_todos_html(todos, filter_type)
            return HTMLResponse(content=html_content)
        
        return {
            "reply": (
                response if isinstance(response, str)
                else str(response) if response is not None
                else "No response generated."
            )
        }
    
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error in chat endpoint: {error_trace}")
        return JSONResponse(
            status_code=500,
            content={"error": f"An error occurred: {str(e)}", "details": error_trace}
        )


@app.get("/my_todos")
async def get_my_todos(user_from_token=Depends(verify_token), format: str = "json"):
    """
    Get user's todos.
    format: 'json' or 'html'
    """
    try:
        user_id = user_from_token.get("user_id")
        todos = list(db.todos.find({"user_id": user_id}))
        
        for t in todos:
            t["_id"] = str(t["_id"])
            if 'planned_time' in t:
                try:
                    dt = datetime.fromisoformat(t['planned_time'])
                    t['planned_time_formatted'] = dt.strftime("%B %d, %Y at %I:%M %p")
                except:
                    t['planned_time_formatted'] = t['planned_time']
        
        if format == "html":
            html_content = generate_todos_html(todos, "all")
            return HTMLResponse(content=html_content)
        
        return {"todos": todos, "status": "success", "count": len(todos)}
    
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error in get_my_todos: {error_trace}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to fetch todos: {str(e)}"}
        )


@app.get("/todos_html")
async def get_todos_html_view(user_from_token=Depends(verify_token), filter: str = "all"):
    """
    Get HTML view of todos.
    filter: 'all', 'pending', or 'completed'
    """
    try:
        user_id = user_from_token.get("user_id")
        todos = list(db.todos.find({"user_id": user_id}))
        
        for t in todos:
            t["_id"] = str(t["_id"])
        
        html_content = generate_todos_html(todos, filter)
        return HTMLResponse(content=html_content)
    
    except Exception as e:
        return HTMLResponse(
            content=f"<html><body><h1>Error</h1><p>{str(e)}</p></body></html>",
            status_code=500
        )


# --------------------------
# Run server
# --------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)