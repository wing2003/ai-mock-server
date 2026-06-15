class RuntimeState:
    """运行时状态管理器"""
    def __init__(self):
        self.active_scene_id = None
        self.is_running = False

    def start_scene(self, scene_id: int):
        self.active_scene_id = scene_id
        self.is_running = True

    def stop_scene(self):
        self.active_scene_id = None
        self.is_running = False

# 全局单例
runtime_state = RuntimeState()
