class YXPlanner:
    def __init__(self, agent):
        self.agent = agent

    def generate(self, start, goal): 
        """
        YX 방식으로 경로를 생성.
        Y 방향 이동 후 X 방향으로 이동.
        """
        waypoints = []
        current_x, current_y = start
        target_x, target_y = goal

        if current_y != target_y:
            waypoints.append((current_x, target_y))
        
        if current_x != target_x:
            waypoints.append((target_x, target_y))
        
        return waypoints
