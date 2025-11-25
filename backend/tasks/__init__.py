"""异步任务定义包。

该包中的函数会被 RQ worker 导入并执行。
每个任务函数都是独立的、无状态的，通过 TaskStore 进行状态管理。

使用方式:
    1. 在 Flask 应用中将任务入队:
       ```python
       from backend.task_queue import get_outline_queue, get_image_queue
       from backend.tasks import generate_outline_task, generate_images_task

       # 大纲任务
       outline_queue = get_outline_queue()
       outline_queue.enqueue(generate_outline_task, task_id, topic)

       # 图片任务
       image_queue = get_image_queue()
       image_queue.enqueue(generate_images_task, task_id)
       ```

    2. 启动 RQ worker:
       ```bash
       rq worker outline_queue image_queue --with-scheduler
       ```
"""

from __future__ import annotations

from .outline_tasks import generate_outline_task
from .image_tasks import generate_images_task

__all__ = [
    "generate_outline_task",
    "generate_images_task",
]
