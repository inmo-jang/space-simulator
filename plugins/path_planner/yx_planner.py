class YXPlanner:
    def __init__(self, agent):
        self.agent = agent
        self.target_position = None

    def set_target_position(self, target_position):
        self.target_position = target_position

    def generate(self, option='yx'):  # ✅ 매개변수 추가
        """
        YX 방식으로 경로를 생성.
        Y 방향 이동 후 X 방향으로 이동.
        """
        waypoints = []
        current_x, current_y = self.agent.position
        target_x, target_y = self.target_position

        if option == 'yx':  # ✅ 매개변수 처리
            if current_y != target_y:
                waypoints.append((current_x, target_y))
            if current_x != target_x:
                waypoints.append((target_x, target_y))
        elif option == 'xy':
            if current_x != target_x:
                waypoints.append((target_x, current_y))
            if current_y != target_y:
                waypoints.append((target_x, target_y))

        return waypoints
