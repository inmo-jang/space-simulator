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

def layout_tree(node, depth=0, x_offset=0, layout=None, level_widths=None):
    """
    Recursively assign x, y positions to each node for visualization.
    """
    if layout is None:
        layout = {}
    if level_widths is None:
        level_widths = {}

    if depth not in level_widths:
        level_widths[depth] = 0
    else:
        level_widths[depth] += 1

    x = level_widths[depth]
    layout[node] = (x, depth)

    if hasattr(node, 'children'):
        for child in node.children:
            layout_tree(child, depth + 1, x, layout, level_widths)

    return layout

def visualise_bt(agent_id, tree, refresh_interval_ms=10, screen_offset_x=1400, screen_offset_y=0, width=630, height=1000):
    """
    Visualise the given BT tree using tkinter, reading status from node.result.
    The window is positioned to the right of the pygame window.
    """
    window = tk.Tk()
    window.title(f"[BT Viewer] Agent {agent_id}")

    # Place the tkinter window just to the right of the pygame window
    window.geometry(f"{width}x{height}+{screen_offset_x}+{screen_offset_y}")

    canvas = tk.Canvas(window, width=width, height=height, bg="white")
    canvas.pack()


    def draw_tree():
        canvas.delete("all")

        layout = layout_tree(tree)
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

                    # Colour the edge between a running parent-child node
                    parent_status = get_status(parent)
                    child_status = get_status(child)

                    if parent_status == 'RUNNING' and child_status == 'RUNNING':
                        line_color = "blue"
                        line_width = 3
                    else:
                        line_color = "black"
                        line_width = 1

                    canvas.create_line(
                        px + NODE_WIDTH / 2, py + NODE_HEIGHT,
                        cx + NODE_WIDTH / 2, cy,
                        fill=line_color,
                        width=line_width
                    )

        # Draw nodes
        for node, (x, y) in positions.items():
            status = get_status(node)
            colour = COLOR_MAP.get(status, "black")

            if getattr(node, 'type', None) == "Condition":
                canvas.create_oval(x, y, x + NODE_WIDTH, y + NODE_HEIGHT, fill=colour, outline="black")
            else:
                canvas.create_rectangle(x, y, x + NODE_WIDTH, y + NODE_HEIGHT, fill=colour, outline="black")
            # canvas.create_rectangle(x, y, x + NODE_WIDTH, y + NODE_HEIGHT, fill=colour, outline="black")
            canvas.create_text(x + NODE_WIDTH / 2, y + NODE_HEIGHT / 2, text=node.name, font=("Arial", 10), fill="white")

        window.after(refresh_interval_ms, draw_tree)

    draw_tree()
    window.mainloop()