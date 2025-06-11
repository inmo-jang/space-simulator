import tkinter as tk

COLOR_MAP = {
    'RUNNING': "blue",
    'SUCCESS': "green",
    'FAILURE': "red",
    'UNKNOWN': "grey"
}

NODE_WIDTH = 120
NODE_HEIGHT = 30
X_SPACING = 30
Y_SPACING = 50

def get_status(node):
    status = getattr(node, "status", None)
    if hasattr(status, 'name'):
        return status.name
    return "UNKNOWN"

def layout_tree(node, direction, depth=0, offset=0, layout=None, level_tracker=None):
    """
    Recursively assigns layout positions to nodes in either direction.
    """
    if layout is None:
        layout = {}
    if level_tracker is None:
        level_tracker = {}

    if depth not in level_tracker:
        level_tracker[depth] = 0
    else:
        level_tracker[depth] += 1

    axis_pos = level_tracker[depth]
    if direction == "Horizontal":
        layout[node] = (depth, axis_pos)
    else:
        layout[node] = (axis_pos, depth)

    if hasattr(node, 'children'):
        for child in node.children:
            layout_tree(child, direction, depth + 1, axis_pos, layout, level_tracker)

    return layout

def visualise_bt(agent_id, tree, direction="Vertical", refresh_interval_ms=10,
                         screen_offset_x=1400, screen_offset_y=0, width=920, height=1000):

    window = tk.Tk()
    window.title(f"[BT Viewer] Agent {agent_id}")
    window.geometry(f"{width}x{height}+{screen_offset_x}+{screen_offset_y}")
    canvas = tk.Canvas(window, width=width, height=height, bg="white")
    canvas.pack()

    def draw_tree():
        canvas.delete("all")

        layout = layout_tree(tree, direction=direction)
        positions = {}

        for node, (x, y) in layout.items():
            abs_x = x * (NODE_WIDTH + X_SPACING) + X_SPACING
            abs_y = y * (NODE_HEIGHT + Y_SPACING) + Y_SPACING
            positions[node] = (abs_x, abs_y)

        # Draw edges between parent and children
        for parent, (px, py) in positions.items():
            if hasattr(parent, 'children'):
                for child in parent.children:
                    cx, cy = positions[child]

                    parent_status = get_status(parent)
                    child_status = get_status(child)
                    line_color = "blue" if parent_status == child_status == "RUNNING" else "black"
                    line_width = 3 if line_color == "blue" else 1

                    if direction == "Horizontal":
                        canvas.create_line(px + NODE_WIDTH, py + NODE_HEIGHT / 2,
                                           cx, cy + NODE_HEIGHT / 2,
                                           fill=line_color, width=line_width)
                    else:
                        canvas.create_line(px + NODE_WIDTH / 2, py + NODE_HEIGHT,
                                           cx + NODE_WIDTH / 2, cy,
                                           fill=line_color, width=line_width)

        # Draw nodes
        for node, (x, y) in positions.items():
            status = get_status(node)
            colour = COLOR_MAP.get(status, "black")

            if getattr(node, 'type', None) == "Condition":
                canvas.create_oval(x, y, x + NODE_WIDTH, y + NODE_HEIGHT, fill=colour, outline="black")
            else:
                canvas.create_rectangle(x, y, x + NODE_WIDTH, y + NODE_HEIGHT, fill=colour, outline="black")

            canvas.create_text(x + NODE_WIDTH / 2, y + NODE_HEIGHT / 2,
                               text=node.name, font=("Arial", 10), fill="white")

        window.after(refresh_interval_ms, draw_tree)

    draw_tree()
    window.mainloop()
