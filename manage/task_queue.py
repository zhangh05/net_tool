"""Task queue and tracking for Manage → NetOps multi-agent orchestration."""

import uuid
import threading
from datetime import datetime

# In-memory task store
_tasks = {}
_tasks_lock = threading.Lock()


class Task:
    def __init__(self, task_id, project_id, goal, plan=None):
        self.task_id = task_id
        self.project_id = project_id
        self.goal = goal
        self.plan = plan or []
        self.status = "pending"  # pending | running | completed | failed
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.steps = []  # list of step results
        self.result = None  # final MiniMax analysis
        self.error = None
        self.retry_count = 0

    def to_dict(self):
        return {
            "task_id": self.task_id,
            "project_id": self.project_id,
            "goal": self.goal,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "steps": self.steps,
            "result": self.result,
            "error": self.error,
            "retry_count": self.retry_count
        }


def create_task(project_id, goal, plan=None):
    """Create a new task and return its ID."""
    task_id = "task_" + str(uuid.uuid4())[:12]
    with _tasks_lock:
        _tasks[task_id] = Task(task_id, project_id, goal, plan)
    return task_id


def get_task(task_id):
    """Get task by ID."""
    with _tasks_lock:
        return _tasks.get(task_id)


def update_task(task_id, **kwargs):
    """Update task fields."""
    with _tasks_lock:
        t = _tasks.get(task_id)
        if t:
            for k, v in kwargs.items():
                setattr(t, k, v)
            t.updated_at = datetime.now()


def list_tasks(project_id=None, limit=50):
    """List tasks, optionally filtered by project."""
    with _tasks_lock:
        tasks = list(_tasks.values())
    if project_id:
        tasks = [t for t in tasks if t.project_id == project_id]
    tasks.sort(key=lambda t: t.updated_at, reverse=True)
    return [t.to_dict() for t in tasks[:limit]]


def cleanup_old_tasks(max_age_seconds=3600):
    """Remove tasks older than max_age_seconds."""
    now = datetime.now()
    with _tasks_lock:
        to_remove = [
            tid for tid, t in _tasks.items()
            if (now - t.updated_at).total_seconds() > max_age_seconds
        ]
        for tid in to_remove:
            del _tasks[tid]
