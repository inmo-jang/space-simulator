# ppa_bt_expansion.py
from modules.base_bt_nodes import config, Fallback, Sequence, BTNodeList
from modules.utils import ResultSaver
from xml.dom import minidom
import xml.etree.ElementTree as ET
import csv
import os
import importlib
bt_module = importlib.import_module(config.get('scenario').get('environment') + ".bt_nodes")
result_saver = ResultSaver(config_file_path="/path/to/config.yaml")  #TODO: Needs debug

# Algorithm 2: LoadLibrary Function
def load_library(csv_file_path):
    ppa_library = {}
    with open(csv_file_path, "r") as csvfile:
        csv_data = csv.reader(csvfile)
        header = next(csv_data)  # Read the header row
        
        for row in csv_data:
            Post_condition = row[0]  # First column
            Action = row[1]  # Second column
            Pre_conditions = row[2:]  # All remaining columns from the third onward
            Pre_conditions = [cond.strip() for cond in Pre_conditions if cond.strip()]  # Remove any empty or whitespace-only values

            ppa_library[Post_condition] = {
                "action": Action,
                "pre_conditions": Pre_conditions
            }

    print(f"ppa_library: {ppa_library}")
    return ppa_library


# Algorithm 3: ExpandBehaviorTree Function
def expand_behavior_tree(tree, failed_condition, ppa_library):
    if failed_condition in ppa_library:
        ppa_fail_entry = ppa_library[failed_condition]
        print(f"[DEBUG] Expanding BT for failed condition: {failed_condition}")
        ppa_bt = generate_ppa_bt(failed_condition, ppa_fail_entry)
        tree = replace_node_with_ppa_bt(tree, failed_condition, ppa_bt)

        # Generate file path
        file_path = result_saver.generate_output_filename(extension="xml")

        # Get the plugin class name from config
        decision_plugin_path = config['decision_making']['plugin']
        plugin_class_name = decision_plugin_path.rsplit('.', 1)[-1]

        # Remove the plugin class name from the file name
        directory, filename = os.path.split(file_path)
        filename = filename.replace(f"{plugin_class_name}_", "")  # Remove the plugin name prefix
        filename = f"PA_BT_{filename}"
        file_path = os.path.join(directory, filename)

        # Save the updated BT as an XML file
        save_tree_as_xml(tree, file_path)
    return tree


# Algorithm 4: GeneratePPA_BT Function
def generate_ppa_bt(post_condition, ppa_fail_entry):
    print(f"[DEBUG] Generating PPA-BT for Post_condition: {post_condition}")

    # Create Fallback Node
    fallback = Fallback("Fallback", children=[])

    # Initialize Seqeunce Node
    sequence = None

    # Check if Pre-conditions exist
    if ppa_fail_entry["action"]:
        if ppa_fail_entry["pre_conditions"]:
            sequence = Sequence("Sequence", [])
            # Add Pre-conditions as Sequence Node
            for pre_condition in ppa_fail_entry["pre_conditions"]:
                condition_class = getattr(bt_module, pre_condition)
                condition_node = condition_class(pre_condition, None)
                sequence.children.append(condition_node)

            # Add Action Node
            action_class = getattr(bt_module, ppa_fail_entry["action"])
            action_node = action_class(ppa_fail_entry["action"], None)
            sequence.children.append(action_node)
        else:
            # If no Pre-conditions, directly use Action Node
            action_class = getattr(bt_module, ppa_fail_entry["action"])
            sequence = action_class(ppa_fail_entry["action"], None)

    # Add Post-condition Node to Fallback
    condition_class = getattr(bt_module, post_condition)
    condition_node = condition_class(post_condition, None)
    condition_node.set_expanded()
    fallback.children.append(condition_node)
    # Add Sequence only if it exists (not None)
    if sequence:
        fallback.children.append(sequence)

    return fallback


# Algorithm 5: ReplaceNodeWithPPA_BT Function
def replace_node_with_ppa_bt(tree, failed_condition, ppa_bt):
    if tree.name == failed_condition:
        print(f"[DEBUG] Replacing node: {failed_condition}")
        return ppa_bt

    if hasattr(tree, "children"):
        new_children = []
        for child in tree.children:
            new_child = replace_node_with_ppa_bt(child, failed_condition, ppa_bt)
            new_children.append(new_child)
        tree.children = new_children

    return tree


# Utility: SaveTreeAsXML Function
def save_tree_as_xml(tree, file_path):
    action_nodes = set()
    condition_nodes = set()
    collect_node_definitions(tree, action_nodes, condition_nodes)

    # Create the root element for Groot2
    root = ET.Element("root", {"BTCPP_format": "4"})
    behavior_tree = ET.SubElement(root, "BehaviorTree", {"ID": "main_tree"})
    behavior_tree.append(node_to_xml(tree))

    # Add TreeNodesModel
    tree_nodes_model = ET.SubElement(root, "TreeNodesModel")
    for action in sorted(action_nodes):
        ET.SubElement(tree_nodes_model, "Action", {"ID": action})
    for condition in sorted(condition_nodes):
        ET.SubElement(tree_nodes_model, "Condition", {"ID": condition, "editable": "true"})

    # Generate pretty XML string
    xml_str = ET.tostring(root, encoding="UTF-8")
    parsed_xml = minidom.parseString(xml_str)
    pretty_xml = parsed_xml.toprettyxml(indent="  ", newl="\n")

    # Adjust line breaks after specific tags
    final_xml = adjust_line_breaks(pretty_xml)

    # Save to file
    with open(file_path, "w", encoding="UTF-8") as f:
        f.write(final_xml)


# For SaveTreeAsXML Function: BT node into an xml element
def node_to_xml(node, visited=None):
    if visited is None:
        visited = set()

    # Prevent circular reference
    if id(node) in visited:
        return None
    visited.add(id(node))

    # Create XML Element
    element = ET.Element(node.name)
    if hasattr(node, "children"):
        for child in node.children:
            child_xml = node_to_xml(child, visited)
            if child_xml is not None:
                element.append(child_xml)
    return element


# For SaveTreeAsXML Function: Post-processing the xml structure
def adjust_line_breaks(pretty_xml):
    """Add specific line breaks after </BehaviorTree> and </TreeNodesModel>."""
    lines = pretty_xml.splitlines()
    adjusted_lines = []
    for line in lines:
        adjusted_lines.append(line)
        if line.strip() in {"</BehaviorTree>", "</TreeNodesModel>"}:
            adjusted_lines.append("")  # Add an extra blank line
    return "\n".join(adjusted_lines)


# For SaveTreeAsXML Function: Distinguish between Action nodes and Condition nodes
def collect_node_definitions(tree, action_set, condition_set):
    """Collect unique Action and Condition node IDs based on BTNodeList."""
    if tree.name in BTNodeList.CONDITION_NODES:
        condition_set.add(tree.name)
    elif tree.name in BTNodeList.ACTION_NODES:
        action_set.add(tree.name)

    if hasattr(tree, "children"):
        for child in tree.children:
            collect_node_definitions(child, action_set, condition_set)


# For SaveTreeAsXML Function: Apply indentation
def indent(elem, level=0):
    """Apply pretty printing with indentation."""
    i = "\n" + "  " * level
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        for child in elem:
            indent(child, level + 1)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i

