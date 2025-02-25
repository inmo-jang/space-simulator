import pygame
import networkx as nx
import matplotlib.pyplot as plt

class GridGraph:
    def __init__(self, grid_nodes, grid_size):
        self.grid_nodes = grid_nodes  # 이동 가능한 노드 집합
        self.grid_size = grid_size    # 그리드 크기
        self.graph = nx.Graph()       # 네트워크 그래프 초기화
        self.build_graph()

    def build_graph(self):
        """
        이동 가능한 노드끼리 연결하여 그래프를 생성
        """
        for node in self.grid_nodes:
            x, y = node
            # 상하좌우 이웃 노드 정의
            neighbors = [
                (x + self.grid_size, y),
                (x - self.grid_size, y),
                (x, y + self.grid_size),
                (x, y - self.grid_size)
            ]
            
            # 유효한 노드만 그래프에 추가 (이동 가능한 노드에 포함된 경우만 연결)
            for neighbor in neighbors:
                if neighbor in self.grid_nodes:
                    self.graph.add_edge(node, neighbor)
    
    def draw_graph_on_pygame(self, screen):
        """
        Pygame 창에 네트워크 그래프를 시각화
        """
        for node in self.graph.nodes:
            pygame.draw.circle(screen, (0, 0, 255), node, 3)  # 노드 (파란 점)
            for neighbor in self.graph.neighbors(node):
                pygame.draw.line(screen, (100, 100, 100), node, neighbor, 1)  # 엣지 (회색 선)