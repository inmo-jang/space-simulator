class XYPlanner:
    def __init__(self, grid_graph):
        self.grid_graph = grid_graph  # GridGraph 객체 사용
        
    def generate(self, start, goal):  
        """
        XY 방식으로 경로를 생성.
        X 방향 이동 후 Y 방향으로 이동.
        """
        waypoints = []
        current_x, current_y = start
        target_x, target_y = goal

        # X 방향 먼저 이동
        if current_x != target_x:
            waypoints.append((target_x, current_y))

        # Y 방향 이동
        if current_y != target_y:
            waypoints.append((target_x, target_y))

        return waypoints
