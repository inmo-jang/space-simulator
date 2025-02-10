import heapq
import networkx as nx
from collections import defaultdict

class AStarPlanner:
    def __init__(self, agent):
        self.agent = agent
        self.grid_graph = agent.env.grid_graph  # GridGraph 객체 사용

    def heuristic(self, node, goal):
        """Manhattan 거리 휴리스틱 함수"""
        return abs(node[0] - goal[0]) + abs(node[1] - goal[1])

    def get_closest_valid_node(self, position):
        """주어진 위치에서 가장 가까운 유효한 grid node를 찾음"""
        graph_nodes = list(self.grid_graph.graph.nodes)
        closest_node = min(graph_nodes, key=lambda node: (node[0] - position[0])**2 + (node[1] - position[1])**2)
        return closest_node

    def generate(self, start, goal):
        """A* 알고리즘을 사용하여 최단 경로 생성"""
        graph = self.grid_graph.graph
        start = self.get_closest_valid_node(start)
        goal = self.get_closest_valid_node(goal)

        if start not in graph.nodes or goal not in graph.nodes:
            print(f"Error: Start {start} or Goal {goal} node is not in the grid.")
            return []
        
        # 우선순위 큐 (F값, 노드)로 초기화
        open_set = [(0, start)]
        came_from = {}
        g_score = defaultdict(lambda: float('inf'))
        g_score[start] = 0
        f_score = defaultdict(lambda: float('inf'))
        f_score[start] = self.heuristic(start, goal)
        
        visited = set()  # 중복 방문 방지
        
        while open_set:
            _, current = heapq.heappop(open_set)
            if current in visited:
                continue
            visited.add(current)

            if current == goal:
                return self.smooth_path(self.reconstruct_path(came_from, current))
            
            for neighbor in graph.neighbors(current):
                edge_weight = graph.get_edge_data(current, neighbor).get("weight", 1)  # 가중치 반영
                tentative_g_score = g_score[current] + edge_weight

                if tentative_g_score < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g_score
                    f_score[neighbor] = tentative_g_score + self.heuristic(neighbor, goal)
                    heapq.heappush(open_set, (f_score[neighbor], neighbor))
        
        return []  # 경로를 찾을 수 없을 경우 빈 리스트 반환
    
    def reconstruct_path(self, came_from, current):
        """경로를 역추적하여 반환"""
        path = [current]
        while current in came_from:
            current = came_from[current]
            path.append(current)
        path.reverse()
        return path

    def smooth_path(self, path):
        """경로 스무딩: 직선 경로 단순화 적용"""
        if len(path) < 3:
            return path  # 너무 짧은 경로는 그대로 반환

        smoothed_path = [path[0]]
        for i in range(1, len(path) - 1):
            prev, curr, next_ = path[i - 1], path[i], path[i + 1]
            if not self.is_line(prev, curr, next_):
                smoothed_path.append(curr)
        smoothed_path.append(path[-1])
        return smoothed_path

    def is_line(self, a, b, c):
        """세 점 (a, b, c)이 일직선상에 있는지 확인"""
        return (a[0] - b[0]) * (b[1] - c[1]) == (b[0] - c[0]) * (a[1] - b[1])
