class PathPlannerPluginManager:
    def __init__(self):
        # 등록된 플러그인 저장소
        self.planners = {}

    def register_planner(self, name, planner_class):
        """
        경로 계획 플러그인을 등록
        :param name: 플러그인 이름 (e.g., "xy", "yx" , "a_star")
        :param planner_class: 경로 계획 알고리즘 클래스
        """
        self.planners[name] = planner_class

    def get_planner(self, name, grid_graph):
        """
        등록된 플러그인 인스턴스 반환
        :param name: 플러그인 이름
        :param grid_graph: Grid 환경 인스턴스
        :return: 선택된 플러그인의 인스턴스
        """
        if name not in self.planners:
            raise ValueError(f"Planner '{name}' is not registered.")
        return self.planners[name](grid_graph)

# 플러그인 매니저 생성 및 플러그인 등록
from .xy_planner import XYPlanner
from .yx_planner import YXPlanner
from .a_star_planner import AStarPlanner


planner_manager = PathPlannerPluginManager()
planner_manager.register_planner("xy", XYPlanner)
planner_manager.register_planner("yx", YXPlanner)
planner_manager.register_planner("a_star", AStarPlanner)